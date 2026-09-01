import os
import sys

# Permite `pytest -q` a partir da raiz sem instalar o pacote.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
