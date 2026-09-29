THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(THIS_DIR)/../../../..)

SIM ?= verilator

TOPLEVEL_LANG = verilog

VERILOG_SOURCES = \
	$(REPO_ROOT)/design/RegPack.sv \
	$(filter-out $(REPO_ROOT)/design/RegPack.sv,$(sort $(wildcard $(REPO_ROOT)/design/*.sv))) \
	$(sort $(wildcard $(REPO_ROOT)/design/*.v)) \
	$(REPO_ROOT)/research/week10/rtl/adaptive_execution_stream_tb.sv

TOPLEVEL = adaptive_execution_stream_tb
MODULE = test_m2_preflight_exact_cut

SIM_BUILD := $(REPO_ROOT)/sim_build/week14_m2_weighted_rtl_smoke

export PYTHONPATH := $(THIS_DIR):$(REPO_ROOT):$(PYTHONPATH)

ifeq ($(SIM),verilator)
COMPILE_ARGS += -Wno-fatal
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
