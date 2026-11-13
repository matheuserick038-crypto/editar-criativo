"""Funções compartilhadas do kit editar-criativo."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
SFX_DIR = KIT_DIR / "sfx"
CONFIG_DIR = Path.home() / ".config" / "editar-criativo"
CONFIG_FILE = CONFIG_DIR / ".env"
RAIZ_PADRAO = Path.home() / "Documents" / "Ofertas"
WHISPER_PY = Path.home() / ".cache" / "watch" / "whisperx-venv" / "Scripts" / "python.exe"

LARGURA, ALTURA, FPS = 1080, 1920, 30

PASTAS = [
    "_work",              # temporários de renderização
    "01_prontos",         # criativos finais (.mp4)
    "02_brutos",          # vídeos de referência / b-roll baixados
    "03_apresentadora",   # gravações de UGC / apresentadora
    "04_imagens",         # imagens do produto
    "05_audios",          # narrações geradas ou enviadas
    "06_efeitos",         # efeitos sonoros e música
    "07_roteiros",        # lotes de roteiros (.json)
    "08_validados",       # criativos que já vendem (base para variações)
]

EXT_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
EXT_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

FONTES = {
    "legenda": [r"C:\Windows\Fonts\seguibl.ttf", r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
    "gancho": [r"C:\Windows\Fonts\seguibl.ttf", r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
}


def configurar_saida() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def log(msg: str) -> None:
    print(f"[criativo] {msg}", file=sys.stderr, flush=True)


def fonte(tipo: str) -> str:
    for caminho in FONTES[tipo]:
        if Path(caminho).is_file():
            return caminho
    raise SystemExit(f"Nenhuma fonte encontrada para '{tipo}'. Instale Segoe UI Black ou Arial Black.")


def binario(nome: str) -> str:
    achado = shutil.which(nome)
    if achado:
        return achado
    # winget instala fora do PATH da sessão atual; procura no PATH persistido.
    for escopo in ("User", "Machine"):
        try:
            import winreg  # noqa: PLC0415
            raiz = winreg.HKEY_CURRENT_USER if escopo == "User" else winreg.HKEY_LOCAL_MACHINE
            sub = "Environment" if escopo == "User" else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            with winreg.OpenKey(raiz, sub) as chave:
                valor, _ = winreg.QueryValueEx(chave, "Path")
            for pasta in os.path.expandvars(valor).split(";"):
                candidato = Path(pasta) / f"{nome}.exe"
                if pasta and candidato.is_file():
                    return str(candidato)
        except (OSError, ImportError):
            continue
    raise SystemExit(f"'{nome}' não encontrado. Instale com: winget install --id Gyan.FFmpeg --exact")


def rodar(cmd: list, *, silencioso: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0:
        cauda = (resultado.stderr or resultado.stdout or "")[-2500:]
        raise SystemExit(f"Falhou ({Path(cmd[0]).name}, exit {resultado.returncode}):\n{cauda}")
    if not silencioso and resultado.stderr:
        print(resultado.stderr, file=sys.stderr)
    return resultado


def ffmpeg(*args) -> None:
    rodar([binario("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args])


def duracao(caminho: Path) -> float:
    r = rodar([binario("ffprobe"), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(caminho)])
    return float(r.stdout.strip())


def tem_audio(caminho: Path) -> bool:
    r = rodar([binario("ffprobe"), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
               "-of", "csv=p=0", str(caminho)])
    return bool(r.stdout.strip())


def ler_env() -> dict:
    valores = {}
    if CONFIG_FILE.is_file():
        for linha in CONFIG_FILE.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def config(chave: str, padrao: str = "") -> str:
    return os.environ.get(chave) or ler_env().get(chave) or padrao


def ler_json(caminho: Path) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8-sig"))


def gravar_json(caminho: Path, dados) -> None:
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def pasta_oferta(lote: Path) -> Path:
    """Os lotes ficam em <oferta>/07_roteiros/; a oferta é o avô do arquivo."""
    lote = Path(lote).resolve()
    if lote.parent.name == "07_roteiros":
        return lote.parent.parent
    dados = ler_json(lote)
    if dados.get("pasta_oferta"):
        return Path(dados["pasta_oferta"])
    raise SystemExit("Não consegui deduzir a pasta da oferta: coloque o lote em <oferta>/07_roteiros/.")


def resolver(oferta: Path, caminho: str) -> Path:
    p = Path(caminho)
    return p if p.is_absolute() else (oferta / p)


def listar_midias(oferta: Path, pastas=("02_brutos", "04_imagens", "03_apresentadora")) -> list[Path]:
    achados = []
    for nome in pastas:
        pasta = oferta / nome
        if pasta.is_dir():
            for arq in sorted(pasta.rglob("*")):
                if arq.suffix.lower() in EXT_VIDEO | EXT_IMAGEM:
                    achados.append(arq)
    return achados
