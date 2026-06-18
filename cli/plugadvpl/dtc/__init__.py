"""dtc — leitor/exporter de .dtc (FairCom c-tree ISAM) standalone.

Vendorizado do projeto dtcat (https://github.com/tbarbito/dtcat, MIT) e
re-namespeado para o pacote `plugadvpl`. Exposto via `plugadvpl dtc *`.

O parser DODA nativo lê arquivos `.dtc` Protheus (fixed-length) em Python
puro — sem AppServer, sem driver, sem FairCom. O caminho c-tree (servidor +
driver nativo) é apenas fallback para arquivos de layout variável.

Atribuição completa em NOTICE (raiz do monorepo).
"""

# Versão do engine dtcat vendorizado (independe da versão do plugadvpl).
__version__ = "0.5.0"
