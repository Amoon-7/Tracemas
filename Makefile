.PHONY: test demo bench bench-quick graph
test:        ; python -m pytest -q
demo:        ; python -m tracemas demo --seed 11 --inject --out out
bench:       ; python -m tracemas benchmark --out results
bench-quick: ; python -m tracemas benchmark --quick --out results
graph:       ; dot -Tpng out/provenance.dot -o out/provenance.png
