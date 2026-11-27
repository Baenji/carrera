import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ordner = Path(__file__).parent   # der Ordner sim/

subprocess.Popen([sys.executable, "-m", "tensorboard.main", "--logdir", "tb_logs"], cwd=ordner)   # TensorBoard
time.sleep(3)                                                                                      # kurz warten, bis TensorBoard bereit ist
webbrowser.open("http://localhost:6006")                                                           # Browser öffnen
subprocess.run([sys.executable, "train.py"], cwd=ordner)                                           # Training
