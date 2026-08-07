POLL ?= $(shell python3 -c "import json;ws=json.load(open('data/raw/waves.json'));print(sorted(ws,key=lambda w:w['wave'])[-1]['file'])")
PADRON ?= data/raw/padron_encarnacion_2026.xlsx
OUT ?= data/output

export PYTHONPATH := src

all:
	python3 -m pollencar.cli run --poll $(POLL) --padron $(PADRON) --out $(OUT)

fast:
	python3 -m pollencar.cli run --poll $(POLL) --padron $(PADRON) --out $(OUT) --fast --skip-negctrl

test:
	python3 -m tests.run_all

.PHONY: all fast test
