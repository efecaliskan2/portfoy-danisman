"""Sadece web sunucusunu çalıştırır (masaüstü penceresi açmadan).
Tarayıcıdan kullanmak veya test için: python serve.py
"""
import sys
from app.server import run

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    print(f"Sunucu: http://127.0.0.1:{port}")
    run(port=port)
