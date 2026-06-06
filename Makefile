.PHONY: install test workbench event

install:
	pip install -r requirements.txt

test:
	pytest

workbench:
	python workbench.py

event:
	python event.py
