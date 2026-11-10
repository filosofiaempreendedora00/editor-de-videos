"""Baixa arquivos do Wikimedia Commons (original ou largura w): commons_get.py <pasta> "File:Nome.jpg|1800" ...
Imprime nome, tamanho, licença e autor (para o crédito)."""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "EditorDeVideos/1.0 (https://www.mediawiki.org/wiki/API:Etiquette; uso pessoal)"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90).read()


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for title in sys.argv[2:]:
        w = None
        if "|" in title:
            title, w = title.split("|")
        q = {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "format": "json"}
        if w:
            q["iiurlwidth"] = w
        try:
            d = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(q)))
            ii = next(iter(d["query"]["pages"].values()))["imageinfo"][0]
            name = title.split(":", 1)[1].replace(" ", "_")
            (out / name).write_bytes(get(ii.get("thumburl") or ii["url"]))
            md = ii.get("extmetadata", {})
            lic = md.get("LicenseShortName", {}).get("value", "")
            art = re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", ""))[:80].replace("\n", " ")
            print(f"{name}  {ii['width']}x{ii['height']}  {lic}  {art}")
        except Exception as e:  # noqa: BLE001
            print(f"✗ {title}: {e}")


if __name__ == "__main__":
    main()
