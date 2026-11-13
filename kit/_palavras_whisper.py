"""Roda DENTRO do venv do WhisperX (faster-whisper). Saída: JSON de palavras com tempos.

Uso: <venv-python> _palavras_whisper.py <midia> <saida.json> <idioma> <ffmpeg>
O áudio é decodificado com ffmpeg (16 kHz mono float32) e entregue como array, evitando o
decodificador PyAV do faster-whisper (incompatível com PyAV 19+).
"""
import json
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel

midia, saida, idioma, ffmpeg = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
bruto = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", midia,
                        "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
audio = np.frombuffer(bruto, dtype=np.float32)
modelo = WhisperModel("small", device="cpu", compute_type="int8")
segmentos, _info = modelo.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True)
palavras = []
for seg in segmentos:
    for p in seg.words or []:
        texto = p.word.strip()
        if texto:
            palavras.append({"t": texto, "ini": round(p.start, 3), "fim": round(p.end, 3)})
with open(saida, "w", encoding="utf-8") as f:
    json.dump({"palavras": palavras}, f, ensure_ascii=False, indent=1)
