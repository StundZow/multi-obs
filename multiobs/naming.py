"""Nom des fichiers d'enregistrement : NOM-TYPE-VIDEO-DATE, appliqué à toutes les instances."""
import re
import time

REC_TYPES = [("cam", "Cam"), ("ecran", "Écran"), ("broll", "B-roll")]
REC_TYPE_LABELS = dict(REC_TYPES)
DEFAULT_TEMPLATE = "{user}-{type}-{video}-{date}_{time}"

# Équivalents des marqueurs de date d'OBS, pour l'aperçu.
_OBS_DATE = {"{date}": "%CCYY-%MM-%DD", "{time}": "%hh-%mm-%ss"}


def clean(text: str) -> str:
    """Retire ce qui est interdit dans un nom de fichier (et % qu'OBS interpréterait)."""
    return re.sub(r'[\\/:*?"<>|%]+', "", text).strip()


def guess_type(name: str) -> str:
    n = name.lower()
    if "ecran" in n or "écran" in n or "screen" in n:
        return "ecran"
    if "broll" in n or "b-roll" in n:
        return "broll"
    return "cam"


def _collapse(s: str) -> str:
    # Champs vides : « Bernard--2026 » -> « Bernard-2026 ».
    s = re.sub(r"([-_ ])[-_ ]+", r"\1", s)
    return s.strip("-_ ") or "Enregistrement"


def obs_format(template: str, user: str, rec_type: str, video: str, suffix: str = "") -> str:
    """Format passé à OBS (FilenameFormatting) ; OBS remplace la date au début du rec."""
    s = (template or DEFAULT_TEMPLATE)
    s = s.replace("{user}", clean(user)).replace("{type}", rec_type).replace("{video}", clean(video))
    for k, v in _OBS_DATE.items():
        s = s.replace(k, v)
    s = _collapse(s)
    if suffix:
        s += "-" + clean(suffix)
    return s


def preview(template: str, user: str, rec_type: str, video: str, suffix: str = "") -> str:
    fmt = obs_format(template, user, rec_type, video, suffix)
    now = time.localtime()
    repl = {"%CCYY": time.strftime("%Y", now), "%MM": time.strftime("%m", now),
            "%DD": time.strftime("%d", now), "%hh": time.strftime("%H", now),
            "%mm": time.strftime("%M", now), "%ss": time.strftime("%S", now)}
    for k, v in repl.items():
        fmt = fmt.replace(k, v)
    return fmt
