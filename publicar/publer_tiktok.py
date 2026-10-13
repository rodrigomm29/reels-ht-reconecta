#!/usr/bin/env python3
"""Invólucro do TikTok: a mesma linha de comando de antes, agora servida pelo publer_postar.py com --rede tiktok
fixo. Toda a lógica (upload em blocos, miniaturas, job_status, trava da fila, "agendando" antes do POST,
conciliação via GET /posts, compare-and-swap, SIGHUP/SIGTERM, --simular, --forcar, --repetir-erros, conferência
de conta) mora no publer_postar.py; aqui não há código de postagem.

Por que invólucro (06/10/2026): um único código pras duas redes evita duas cópias da proteção contra post
duplicado ficarem diferentes com o tempo; quem já usava este comando não muda nada.

uso (igual a antes; --intervalo MIN com --por-dia N também vale aqui):
  python3 publer_tiktok.py contas
  python3 publer_tiktok.py postar SEM41-terca --inicio "2026-10-07 09:00" --simular
  python3 publer_tiktok.py postar SEM41-terca --de VD004_B --max 3 --inicio "2026-10-07 09:00" --por-dia 3 --horarios "09:00,13:00,19:00"
  python3 publer_tiktok.py postar SEM41-terca --inicio "2026-10-08 09:00" --forcar VD005_A    (só depois de conferir o Publer)
  python3 publer_tiktok.py autoteste      (o autoteste completo: TikTok e Instagram)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publer_postar  # noqa: E402

if __name__ == '__main__':
    sys.exit(publer_postar.main(rede_fixa='tiktok'))
