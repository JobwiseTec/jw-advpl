"""Testes de cli/plugadvpl/parsing/ini.py.

Cobertura:
    - Parser core (seções ativas, seções comentadas, merge case-insensitive,
      chave inválida, valor vazio com exceção legítima).
    - Encoding detection (BOM utf-8, utf-16, utf-8 puro, ascii, cp1252).
    - Detecção de tipo (appserver/dbaccess/smartclient/tss/broker/custom).
    - Detecção de role (14 possíveis).
    - Comentários (above, inline, post-key).
"""
from __future__ import annotations

import pytest

from plugadvpl.parsing.ini import (
    analyze_encoding,
    decode_ini_bytes,
    is_protheus_ini_filename,
    parse_ini_file,
)


# =============================================================================
# Encoding
# =============================================================================


class TestEncoding:
    def test_utf8_bom_detected(self) -> None:
        info = analyze_encoding(b"\xef\xbb\xbf[Section]\nKey=Value\n")
        assert info.detected == "utf-8-bom"
        assert info.has_bom is True
        assert any("BOM UTF-8" in w for w in info.warnings)

    def test_utf16_detected(self) -> None:
        info = analyze_encoding(b"\xff\xfe[\x00S\x00")
        assert info.detected == "utf-16"
        assert info.has_bom is True

    def test_ascii_pure(self) -> None:
        info = analyze_encoding(b"[General]\nKey=Value\n")
        assert info.detected == "ascii"
        assert info.warnings == []

    def test_utf8_without_bom_warns(self) -> None:
        info = analyze_encoding("[General]\nName=João\n".encode("utf-8"))
        assert info.detected == "utf-8"
        assert any("UTF-8 sem BOM" in w for w in info.warnings)

    def test_cp1252_fallback(self) -> None:
        # 0xE9 = é em cp1252, sequência inválida em utf-8
        info = analyze_encoding(b"[General]\nName=Jos\xe9\n")
        assert info.detected == "cp1252"

    def test_decode_strips_bom(self) -> None:
        decoded = decode_ini_bytes(b"\xef\xbb\xbf[X]\n")
        assert decoded.startswith("[X]"), "BOM deveria ter sido removido"

    def test_decode_cp1252_fallback(self) -> None:
        decoded = decode_ini_bytes(b"Name=Jos\xe9\n")
        assert "José" in decoded


# =============================================================================
# Parser core
# =============================================================================


class TestParserCore:
    def test_simple_section_with_keys(self) -> None:
        p = parse_ini_file("[General]\nKey1=Value1\nKey2=Value2\n", filename="x.ini")
        assert len(p.sections) == 1
        assert p.sections[0].name_raw == "General"
        assert p.sections[0].commented is False
        assert len(p.keys) == 2
        assert p.keys[0].key_name == "Key1"
        assert p.keys[0].value == "Value1"
        assert p.dirty_lines == []

    def test_commented_section_keys_inactive(self) -> None:
        p = parse_ini_file(
            ";[DeadSection]\nKey1=NotCounted\n\n[Active]\nKey2=Counted\n",
            filename="x.ini",
        )
        # 2 seções (uma comentada, uma ativa)
        sec_by_norm = p.sections_by_name_norm
        assert sec_by_norm["deadsection"].commented is True
        assert sec_by_norm["active"].commented is False
        # Chave de seção comentada NÃO aparece em keys
        keys_in_active = [k for k in p.keys if k.section_name.lower() == "active"]
        assert len(keys_in_active) == 1
        assert keys_in_active[0].key_name == "Key2"

    def test_merge_case_insensitive_sections(self) -> None:
        # [TSSTaskProc] e [tsstaskproc] devem virar a mesma seção
        content = (
            "[TSSTaskProc]\nKey1=V1\n\n"
            "[tsstaskproc]\nKey2=V2\n"
        )
        p = parse_ini_file(content, filename="tss.ini")
        # 1 seção (merge) + name_raw preserva o primeiro
        sec_names_norm = {s.name_norm for s in p.sections}
        assert sec_names_norm == {"tsstaskproc"}
        assert p.sections_by_name_norm["tsstaskproc"].name_raw == "TSSTaskProc"
        # As 2 keys ainda aparecem (referenciam a mesma seção)
        keys_count = len([k for k in p.keys if k.section_name.lower() == "tsstaskproc"])
        assert keys_count == 2

    def test_invalid_key_name_marked_dirty(self) -> None:
        p = parse_ini_file("[General]\n123=Bad\nGood=OK\n", filename="x.ini")
        assert any("invalido" in d.reason for d in p.dirty_lines)
        # Mas a key inválida não vai pra `keys`
        assert all(k.key_name != "123" for k in p.keys)

    def test_empty_value_in_general_is_dirty(self) -> None:
        p = parse_ini_file("[General]\nMyKey=\n", filename="x.ini")
        assert any("vazio" in d.reason for d in p.dirty_lines)

    def test_empty_value_in_mssql_driver_ok_for_tablespace(self) -> None:
        p = parse_ini_file(
            "[MSSQL/myenv]\nUser=admin\nTableSpace=\nIndexSpace=\n",
            filename="x.ini",
        )
        # tablespace/indexspace vazios em MSSQL são legítimos (não-Oracle)
        assert not any("TableSpace" in d.content for d in p.dirty_lines)
        assert not any("IndexSpace" in d.content for d in p.dirty_lines)

    def test_inline_comment_captured(self) -> None:
        p = parse_ini_file(
            "[General]\nPort=4301 ; valor padrao Protheus\n",
            filename="x.ini",
        )
        k = next(k for k in p.keys if k.key_name == "Port")
        assert k.value == "4301"
        assert "padrao" in k.comment_inline

    def test_comment_above_captured(self) -> None:
        p = parse_ini_file(
            "[General]\n; nota do dev\n; segunda nota\nPort=4301\n",
            filename="x.ini",
        )
        k = next(k for k in p.keys if k.key_name == "Port")
        assert "nota do dev" in k.comment_above
        assert "segunda nota" in k.comment_above

    def test_line_outside_section_is_dirty(self) -> None:
        p = parse_ini_file("StrayKey=Value\n[Section]\nGood=OK\n", filename="x.ini")
        assert any("fora de qualquer secao" in d.reason for d in p.dirty_lines)

    def test_empty_input_returns_empty_parsed(self) -> None:
        p = parse_ini_file("", filename="empty.ini")
        assert p.sections == []
        assert p.keys == []
        assert p.dirty_lines == []
        assert p.tipo in {"custom", "appserver", "dbaccess", "smartclient"}


# =============================================================================
# Detecção de tipo
# =============================================================================


class TestDetectIniType:
    def test_tss_by_section(self) -> None:
        p = parse_ini_file("[TSSTaskProc]\nKey=X\n", filename="random.ini")
        assert p.tipo == "tss"

    def test_dbaccess_by_filename(self) -> None:
        p = parse_ini_file("[General]\nMode=master\n", filename="dbaccess.ini")
        assert p.tipo == "dbaccess"

    def test_appserver_by_filename(self) -> None:
        p = parse_ini_file("[General]\nMaxStringSize=1\n", filename="appserver.ini")
        assert p.tipo == "appserver"

    def test_smartclient_by_filename(self) -> None:
        p = parse_ini_file("[Config]\nLastEnv=protheus\n", filename="smartclient.ini")
        assert p.tipo == "smartclient"

    def test_broker_by_balance_sections(self) -> None:
        content = "[balance_http]\nLB_Algorithm=RR\n[balance_node_1]\nIP=10.0.0.1\n"
        p = parse_ini_file(content, filename="anything.ini")
        assert p.tipo == "broker"

    def test_custom_fallback(self) -> None:
        p = parse_ini_file("[Random]\nKey=X\n", filename="anything.ini")
        assert p.tipo == "custom"


# =============================================================================
# Detecção de role
# =============================================================================


class TestDetectIniRole:
    def test_tss_role(self) -> None:
        p = parse_ini_file("[TSSTaskProc]\nKey=X\n", filename="tss.ini")
        assert p.role == "tss"

    def test_dbaccess_master(self) -> None:
        p = parse_ini_file("[General]\nMode=master\n", filename="dbaccess.ini")
        assert p.role == "dbaccess_master"

    def test_dbaccess_slave(self) -> None:
        p = parse_ini_file("[General]\nMode=slave\n", filename="dbaccess.ini")
        assert p.role == "dbaccess_slave"

    def test_dbaccess_standalone_default(self) -> None:
        p = parse_ini_file("[General]\nOther=x\n", filename="dbaccess.ini")
        assert p.role == "dbaccess_standalone"

    def test_broker_http(self) -> None:
        content = (
            "[balance_http]\nLB_Algorithm=RR\n"
            "[balance_node_1]\nIP=10.0.0.1\n"
        )
        p = parse_ini_file(content, filename="broker.ini")
        assert p.role == "broker_http"

    def test_broker_rest_by_filename(self) -> None:
        content = "[balance_web_services]\nLB=RR\n[balance_x]\nIP=10\n"
        p = parse_ini_file(content, filename="broker_rest.ini")
        assert p.role == "broker_rest"

    def test_broker_soap_by_default(self) -> None:
        content = "[balance_web_services]\nLB=RR\n[balance_x]\nIP=10\n"
        p = parse_ini_file(content, filename="broker_soap.ini")
        assert p.role == "broker_soap"

    def test_slave_rest(self) -> None:
        content = (
            "[httprest]\nPort=80\n[httpjob]\nThreads=10\n"
            "[licenseclient]\nServer=l\n[General]\nKey=v\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "slave_rest"

    def test_rest_server_no_licenseclient(self) -> None:
        content = (
            "[httprest]\nPort=80\n[httpjob]\nThreads=10\n[General]\nKey=v\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "rest_server"

    def test_job_server(self) -> None:
        content = (
            "[onstart]\nJobs=job_a,job_b\n"
            "[job_a]\nMain=Routine1\n"
            "[General]\nKey=v\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "job_server"

    def test_slave_when_licenseclient_and_webapp(self) -> None:
        content = (
            "[licenseclient]\nServer=l\n[webapp]\nport=80\n"
            "[General]\nKey=v\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "slave"

    def test_standalone_default(self) -> None:
        # 1 environment, sem indicadores especiais → standalone
        content = (
            "[General]\nKey=v\n"
            "[myenv]\nRootPath=C:\\protheus\\\nSourcePath=C:\\apo\\\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "standalone"

    def test_standalone_multi_env(self) -> None:
        # 3+ environments
        content = (
            "[General]\nKey=v\n"
            "[env1]\nRootPath=A\nSourcePath=B\n"
            "[env2]\nRootPath=A\nSourcePath=B\n"
            "[env3]\nRootPath=A\nSourcePath=B\n"
        )
        p = parse_ini_file(content, filename="appserver.ini")
        assert p.role == "standalone_multi_env"


# =============================================================================
# is_protheus_ini_filename
# =============================================================================


class TestIsProtheusIniFilename:
    @pytest.mark.parametrize("name", [
        "appserver.ini", "dbaccess.ini", "smartclient.ini", "tss.ini", "broker.ini",
        "dev_appserver.ini", "prd_dbaccess.ini", "appserver_qa.ini",
        "prd-broker.ini", "APPSERVER.INI",
    ])
    def test_accepted(self, name: str) -> None:
        assert is_protheus_ini_filename(name) is True

    @pytest.mark.parametrize("name", [
        "config.txt", "appserver.txt", "desktop.ini", "random.ini",
        "config.ini",  # nenhum token
    ])
    def test_rejected(self, name: str) -> None:
        assert is_protheus_ini_filename(name) is False
