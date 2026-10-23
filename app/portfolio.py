"""Portföy dosyası ve günlük geçmiş anlık görüntülerinin (snapshot) yönetimi."""

from __future__ import annotations

import json
from datetime import date  # noqa: F401  (save_portfolio damgası için)
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
HISTORY_PATH = DATA_DIR / "history.json"
BACKUP_PATH = DATA_DIR / "portfolio.backup.json"
EXAMPLE_PATH = DATA_DIR / "portfolio.example.json"


def load_portfolio() -> dict:
    # portfolio.json kişisel veri olduğu için depoya girmez (.gitignore). Taze bir
    # kurulumda yoksa örnek dosyadan kopyalanır; aksi halde uygulama açılışta çöker.
    if not PORTFOLIO_PATH.exists() and EXAMPLE_PATH.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PORTFOLIO_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"),
                                  encoding="utf-8")
    return json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))


def save_portfolio(data: dict) -> None:
    # Her varlığa eklendiği tarihi damgala. Ekstre mutabakatında hayati:
    # ekstre tarihinden SONRA eklenen bir varlık, o ekstrede görünmediği için
    # "satılmış" sanılıp silinmemeli (BKRGY'de tam bu tuzağa düşülüyordu).
    today = date.today().isoformat()
    for h in data.get("holdings", []):
        h.setdefault("added_on", today)
    PORTFOLIO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def backup_portfolio() -> None:
    """Otomatik güncellemeden önceki hali saklar — geri alınabilsin."""
    if PORTFOLIO_PATH.exists():
        BACKUP_PATH.write_text(PORTFOLIO_PATH.read_text(encoding="utf-8"),
                               encoding="utf-8")


def restore_portfolio() -> bool:
    """Son otomatik güncellemeyi geri alır."""
    if not BACKUP_PATH.exists():
        return False
    PORTFOLIO_PATH.write_text(BACKUP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def load_history() -> list:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def record_snapshot(total_value: float, allocation: dict) -> list:
    """Günde bir kez toplam değeri kaydeder; zamanla drawdown/momentum hesaplanır."""
    history = load_history()
    today = date.today().isoformat()
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "total": round(total_value, 2), "allocation": allocation})
    history = history[-400:]  # ~son 1.5 yıl
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history
