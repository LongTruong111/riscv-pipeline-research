
.PHONY: smoke
smoke:
	@printf "finish\n" | bash research/week3/run_smoke3.sh
	@python3 research/week3/check_smoke3.py
