THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(THIS_DIR)/../../..)

SIM ?= verilator
TOPLEVEL_LANG = verilog

CANONICAL_FORWARDING := $(REPO_ROOT)/design/ForwardingUnit.sv
REGPACK := $(REPO_ROOT)/design/RegPack.sv
M1_FORWARDING := $(REPO_ROOT)/research/week12/mutants/ForwardingUnit_m1.sv

DESIGN_SV := $(sort $(wildcard $(REPO_ROOT)/design/*.sv))

VERILOG_SOURCES = \
	$(REGPACK) \
	$(filter-out $(REGPACK) $(CANONICAL_FORWARDING),$(DESIGN_SV)) \
	$(M1_FORWARDING) \
	$(sort $(wildcard $(REPO_ROOT)/design/*.v)) \
	$(REPO_ROOT)/research/week5/rtl/execution_stream_tb.sv

TOPLEVEL = execution_stream_tb
MODULE = test_m1_activation

SIM_BUILD := $(REPO_ROOT)/sim_build/week12_m1_activation

export PYTHONPATH := $(THIS_DIR):$(REPO_ROOT):$(PYTHONPATH)

ifeq ($(SIM),verilator)
COMPILE_ARGS += -Wno-fatal
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
