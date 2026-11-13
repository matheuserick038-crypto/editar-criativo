#!/usr/bin/env python3
"""Busca vídeos e fotos para a oferta: primeiro na BIBLIOTECA LOCAL, depois nos bancos gratuitos.

Uso:
  python buscar_midias.py "<pasta_oferta>" "stretching" [--qtd 6] [--tipo ambos|video|foto]
         [--orientacao vertical|estrito|qualquer] [--duracao-max 40] [--fonte pexels,pixabay]
         [--sem-api] [--forcar-api] [--listar]

Biblioteca: tudo o que é baixado fica em <Ofertas>/_biblioteca (videos/, fotos/, indice.json),
indexado pelas tags do banco + termos buscados. Uma busca nova:
  1. procura na biblioteca itens com TODAS as palavras do termo (tags ou termos anteriores);
  2. só se faltar material chama a API (Pexels/Pixabay) — e itens que a API devolver e já
     estiverem na biblioteca são reaproveitados sem novo download;
  3. liga (hardlink, sem ocupar espaço extra) os arquivos na pasta da oferta:
     vídeos -> 02_brutos/, fotos -> 04_imagens/, créditos -> 02_brutos/creditos.csv.
Chaves (grátis) em ~/.config/editar-criativo/.env: PEXELS_API_KEY, PIXABAY_API_KEY.
Dica: termos em inglês trazem muito mais resultados (e casam com as tags da biblioteca).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from comum import CONFIG_FILE, RAIZ_PADRAO, config, configurar_saida, log

AGENTE = "editar-criativo/1.0"
ALVO_H = 1920
BIBLIOTECA = Path(config("EDITAR_CRIATIVO_BIBLIOTECA", str(RAIZ_PADRAO / "_biblioteca")))
INDICE = BIBLIOTECA / "indice.json"


class SemChave(Exception):
    pass


# ---------------------------------------------------------------- utilidades
def _palavras(texto: str) -> set[str]:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    saida = set()
    for p in re.findall(r"[a-z0-9]+", texto):
        if len(p) > 3 and p.endswith("s") and not p.endswith("ss"):
            p = p[:-1]  # plural simples: candles -> candle
        saida.add(p)
    return saida


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, **(headers or {})})
    host = urllib.parse.urlparse(url).netloc
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit(f"Chave recusada ({e.code}) em {host}: confira a chave no .env") from None
        if e.code == 429:
            raise SystemExit(f"Limite de pedidos atingido em {host}; espere alguns minutos.") from None
        raise SystemExit(f"Erro {e.code} em {host}: {e.read()[:300]!r}") from None


def _baixar(url: str, destino: Path) -> int:
    temp = destino.with_suffix(destino.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=180) as r, open(temp, "wb") as f:
        while bloco := r.read(1 << 16):
            f.write(bloco)
    temp.replace(destino)
    return destino.stat().st_size


def _ligar(origem: Path, destino: Path) -> None:
    """Hardlink (mesmo disco, sem espaço extra); se não der, copia."""
    try:
        os.link(origem, destino)
    except OSError:
        shutil.copy2(origem, destino)


def _nota_arquivo(w: int, h: int) -> float:
    """Menor é melhor: vertical, lado maior perto de 1920, sem desperdiçar banda com 4K."""
    lado = max(w, h)
    return (0 if h > w else 10_000) + abs(lado - ALVO_H) + (5_000 if lado > 2600 else 0)


def _chave(it: dict) -> str:
    return f"{it['fonte']}_{it['tipo']}_{it['id']}"


# ---------------------------------------------------------------- índice da biblioteca
def carregar_indice() -> dict:
    if INDICE.is_file():
        return json.loads(INDICE.read_text(encoding="utf-8"))
    return {}


def gravar_indice(indice: dict) -> None:
    BIBLIOTECA.mkdir(parents=True, exist_ok=True)
    temp = INDICE.with_suffix(".tmp")
    temp.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(INDICE)


def buscar_local(indice: dict, termo: str, tipo: str, dur_max: float, orientacao: str) -> list[dict]:
    alvo = _palavras(termo)
    achados = []
    for chave, it in indice.items():
        if it.get("descartado") or (tipo != "ambos" and it["tipo"] != tipo):
            continue
        if not (BIBLIOTECA / it["arquivo"]).is_file():
            continue
        if it["tipo"] == "video" and dur_max and (it.get("duracao") or 0) > dur_max:
            continue
        if orientacao == "estrito" and (it.get("h") or 0) <= (it.get("w") or 0):
            continue
        palavras = _palavras(" ".join(it.get("tags", []) + it.get("termos", [])))
        if alvo and alvo <= palavras:
            achados.append({**it, "chave": chave, "origem": "biblioteca"})
    if orientacao == "vertical":
        achados.sort(key=lambda it: (it.get("h") or 0) <= (it.get("w") or 0))
    return achados


# ---------------------------------------------------------------- Pexels
def pexels(termo: str, tipo: str, qtd: int, orientacao: str, dur_max: float) -> list[dict]:
    chave = config("PEXELS_API_KEY")
    if not chave:
        raise SemChave("PEXELS_API_KEY")
    h = {"Authorization": chave}
    itens = []
    base = {"query": termo, "per_page": min(max(qtd * 3, 15), 80), "locale": "pt-BR"}
    if orientacao == "estrito":
        base["orientation"] = "portrait"
    if tipo in ("video", "ambos"):
        dados = _get_json("https://api.pexels.com/videos/search?" + urllib.parse.urlencode({**base, "size": "medium"}), h)
        for v in dados.get("videos", []):
            if dur_max and v.get("duration", 0) > dur_max:
                continue
            arquivos = [a for a in v.get("video_files", []) if a.get("link") and a.get("width") and a.get("height")
                        and (a.get("file_type") or "").endswith("mp4")]
            if not arquivos:
                continue
            melhor = min(arquivos, key=lambda a: _nota_arquivo(a["width"], a["height"]))
            if orientacao == "estrito" and melhor["height"] <= melhor["width"]:
                continue
            slug = urllib.parse.urlparse(v.get("url", "")).path.strip("/").split("/")[-1]
            itens.append({"fonte": "pexels", "tipo": "video", "id": v["id"], "url": melhor["link"],
                          "w": melhor["width"], "h": melhor["height"], "duracao": v.get("duration"),
                          "autor": (v.get("user") or {}).get("name", ""), "pagina": v.get("url", ""),
                          "tags": [t for t in slug.split("-") if not t.isdigit()], "ext": ".mp4"})
    if tipo in ("foto", "ambos"):
        dados = _get_json("https://api.pexels.com/v1/search?" + urllib.parse.urlencode(base), h)
        for p in dados.get("photos", []):
            src = p.get("src", {})
            url = src.get("large2x") or src.get("original")
            if url:
                itens.append({"fonte": "pexels", "tipo": "foto", "id": p["id"], "url": url, "w": p.get("width"),
                              "h": p.get("height"), "autor": p.get("photographer", ""), "pagina": p.get("url", ""),
                              "tags": (p.get("alt") or "").split(), "ext": ".jpg"})
    return itens


# ---------------------------------------------------------------- Pixabay
def pixabay(termo: str, tipo: str, qtd: int, orientacao: str, dur_max: float) -> list[dict]:
    chave = config("PIXABAY_API_KEY")
    if not chave:
        raise SemChave("PIXABAY_API_KEY")
    itens = []
    base = {"key": chave, "q": termo[:100], "per_page": min(max(qtd * 3, 20), 200), "safesearch": "true"}
    if tipo in ("video", "ambos"):
        dados = _get_json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(base))
        for v in dados.get("hits", []):
            if dur_max and v.get("duration", 0) > dur_max:
                continue
            versoes = [x for x in (v.get("videos") or {}).values() if x.get("url") and x.get("width") and x.get("height")]
            if not versoes:
                continue
            melhor = min(versoes, key=lambda x: _nota_arquivo(x["width"], x["height"]))
            if orientacao == "estrito" and melhor["height"] <= melhor["width"]:
                continue
            itens.append({"fonte": "pixabay", "tipo": "video", "id": v["id"], "url": melhor["url"],
                          "w": melhor["width"], "h": melhor["height"], "duracao": v.get("duration"),
                          "autor": v.get("user", ""), "pagina": v.get("pageURL", ""),
                          "tags": [t.strip() for t in (v.get("tags") or "").split(",") if t.strip()], "ext": ".mp4"})
    if tipo in ("foto", "ambos"):
        params = {**base, "image_type": "photo"}
        if orientacao in ("vertical", "estrito"):
            params["orientation"] = "vertical"
        dados = _get_json("https://pixabay.com/api/?" + urllib.parse.urlencode(params))
        for p in dados.get("hits", []):
            url = p.get("largeImageURL") or p.get("webformatURL")
            if url:
                ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".jpg"
                itens.append({"fonte": "pixabay", "tipo": "foto", "id": p["id"], "url": url, "w": p.get("imageWidth"),
                              "h": p.get("imageHeight"), "autor": p.get("user", ""), "pagina": p.get("pageURL", ""),
                              "tags": [t.strip() for t in (p.get("tags") or "").split(",") if t.strip()],
                              "ext": ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"})
    return itens


FONTES = {"pexels": pexels, "pixabay": pixabay}


def _registrar(oferta: Path, linhas: list[list]) -> None:
    arq = oferta / "02_brutos" / "creditos.csv"
    novo = not arq.exists()
    with open(arq, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data", "fonte", "tipo", "id", "autor", "pagina", "termo", "arquivo", "origem"])
        w.writerows(linhas)


def _destino_oferta(oferta: Path, it: dict) -> Path:
    pasta = oferta / ("02_brutos" if it["tipo"] == "video" else "04_imagens")
    return pasta / Path(it["arquivo"]).name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("oferta")
    ap.add_argument("termo")
    ap.add_argument("--fonte", default="pexels,pixabay")
    ap.add_argument("--tipo", choices=["ambos", "video", "foto"], default="ambos")
    ap.add_argument("--qtd", type=int, default=6, help="quantos itens NOVOS para a oferta, de cada tipo")
    ap.add_argument("--orientacao", choices=["vertical", "estrito", "qualquer"], default="vertical",
                    help="vertical = prefere vertical e completa com horizontal (o kit recorta); "
                         "estrito = só vertical; qualquer = sem preferência")
    ap.add_argument("--duracao-max", type=float, default=40, help="ignora vídeos mais longos (s); 0 = sem limite")
    ap.add_argument("--sem-api", action="store_true", help="usa só a biblioteca local")
    ap.add_argument("--forcar-api", action="store_true", help="ignora a biblioteca e consulta a API")
    ap.add_argument("--listar", action="store_true", help="só mostra o que seria usado, sem baixar/ligar")
    ap.add_argument("--descartar", nargs="+", metavar="ARQUIVO",
                    help="marca arquivos (nome ou caminho) como ruins na biblioteca e tira da oferta; o termo é ignorado")
    a = ap.parse_args()

    if a.descartar:
        indice = carregar_indice()
        oferta = Path(a.oferta)
        for nome in a.descartar:
            base = Path(nome).name
            ch = next((k for k, v in indice.items() if Path(v["arquivo"]).name == base), None)
            if not ch:
                log(f"não está na biblioteca: {base}")
                continue
            indice[ch]["descartado"] = True
            for sub in ("02_brutos", "04_imagens"):
                ligado = oferta / sub / base
                if ligado.exists():
                    ligado.unlink()  # só o link da oferta; o arquivo continua na biblioteca, marcado
        gravar_indice(indice)
        print(f"Descartados: {len(a.descartar)} (não aparecem mais em buscas)")
        return

    oferta = Path(a.oferta)
    if not (oferta / "02_brutos").is_dir():
        raise SystemExit(f"Pasta de oferta inválida (sem 02_brutos): {oferta}. Rode criar_oferta.py antes.")
    tipos = ["video", "foto"] if a.tipo == "ambos" else [a.tipo]
    indice = carregar_indice()

    # 1) biblioteca local — só conta o que ainda não está nesta oferta
    escolhidos: list[dict] = []
    faltam = {t: a.qtd for t in tipos}
    if not a.forcar_api:
        for it in buscar_local(indice, a.termo, a.tipo, a.duracao_max, a.orientacao):
            if faltam.get(it["tipo"], 0) > 0 and not _destino_oferta(oferta, it).exists():
                escolhidos.append(it)
                faltam[it["tipo"]] -= 1
        log(f"biblioteca: {len(escolhidos)} itens para '{a.termo}' "
            f"(faltam {', '.join(f'{n} {t}' for t, n in faltam.items() if n) or 'nada'})")

    # 2) API só para o que faltar
    tipos_api = [t for t, n in faltam.items() if n > 0]
    if tipos_api and not a.sem_api:
        tipo_api = tipos_api[0] if len(tipos_api) == 1 else "ambos"
        resultados, sem_chave = [], []
        for nome in [f.strip() for f in a.fonte.split(",") if f.strip()]:
            if nome not in FONTES:
                raise SystemExit(f"Fonte desconhecida: {nome} (use pexels, pixabay)")
            try:
                achados = FONTES[nome](a.termo, tipo_api, max(faltam.values()), a.orientacao, a.duracao_max)
                if a.orientacao == "vertical":
                    achados.sort(key=lambda it: (it["h"] or 0) <= (it["w"] or 0))
                log(f"{nome}: {len(achados)} resultados (1 requisição por tipo)")
                resultados.append(achados)
            except SemChave as falta:
                sem_chave.append(str(falta))
        if sem_chave and not resultados:
            raise SystemExit(f"Falta(m) chave(s): {', '.join(sem_chave)}. Cadastre grátis e salve em {CONFIG_FILE}")
        if sem_chave:
            log(f"pulando fontes sem chave: {', '.join(sem_chave)}")
        ja = {it["chave"] for it in escolhidos}
        for i in range(max((len(r) for r in resultados), default=0)):
            for lista in resultados:
                if i >= len(lista):
                    continue
                it = lista[i]
                ch = _chave(it)
                if faltam.get(it["tipo"], 0) <= 0 or ch in ja:
                    continue
                if ch in indice and indice[ch].get("descartado"):
                    continue  # já foi visto e reprovado: não volta
                if ch in indice:  # já baixado antes (outra busca): reaproveita sem baixar
                    it = {**indice[ch], "chave": ch, "origem": "biblioteca"}
                else:
                    sub = "videos" if it["tipo"] == "video" else "fotos"
                    it = {**it, "chave": ch, "origem": it["fonte"], "arquivo": f"{sub}/{ch}{it['ext']}"}
                if _destino_oferta(oferta, it).exists():
                    continue
                escolhidos.append(it)
                ja.add(ch)
                faltam[it["tipo"]] -= 1

    if a.listar:
        for it in escolhidos:
            dur = f" {it['duracao']}s" if it.get("duracao") else ""
            print(f"{it['origem']:10} {it['tipo']:5} {it['w']}x{it['h']}{dur}  {', '.join(it.get('tags', [])[:5])}")
        return

    # 3) baixa o que é novo para a biblioteca e liga tudo na oferta
    hoje = dt.date.today().isoformat()
    linhas, novos, reaproveitados, total = [], 0, 0, 0
    for it in escolhidos:
        na_bib = BIBLIOTECA / it["arquivo"]
        if it["origem"] != "biblioteca":
            na_bib.parent.mkdir(parents=True, exist_ok=True)
            try:
                total += _baixar(it["url"], na_bib)
            except (urllib.error.URLError, OSError) as erro:
                log(f"falhou {it['chave']}: {erro}")
                continue
            indice[it["chave"]] = {k: it.get(k) for k in ("fonte", "tipo", "id", "arquivo", "w", "h", "duracao",
                                                           "autor", "pagina", "tags")}
            indice[it["chave"]]["termos"] = [a.termo]
            indice[it["chave"]]["baixado"] = hoje
            novos += 1
        else:
            termos = indice[it["chave"]].setdefault("termos", [])
            if a.termo not in termos:
                termos.append(a.termo)
            reaproveitados += 1
        destino = _destino_oferta(oferta, it)
        _ligar(na_bib, destino)
        linhas.append([hoje, it["fonte"], it["tipo"], it["id"], it.get("autor", ""), it.get("pagina", ""), a.termo,
                       destino.relative_to(oferta).as_posix(), it["origem"]])
        gravar_indice(indice)  # a cada item: uma interrupção não perde o que já baixou
    if linhas:
        _registrar(oferta, linhas)
    print(f"Na oferta: +{len(linhas)} ({reaproveitados} da biblioteca, {novos} baixados, {total / 1e6:.1f} MB) | "
          f"biblioteca: {len(indice)} itens em {BIBLIOTECA}")
    if any(faltam.values()):
        print(f"Faltou material: {', '.join(f'{n} {t}' for t, n in faltam.items() if n)} — tente outro termo.")


if __name__ == "__main__":
    configurar_saida()
    main()
