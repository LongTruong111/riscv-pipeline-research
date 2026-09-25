THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(THIS_DIR)/../../..)

SIM ?= verilator
TOPLEVEL_LANG = verilog

CANONICAL_FORWARDING := $(REPO_ROOT)/design/ForwardingUnit.sv
M2_FORWARDING := $(REPO_ROOT)/research/week13/mutants/ForwardingUnit_m2.sv
REGPACK := $(REPO_ROOT)/design/RegPack.sv

DESIGN_SV := $(sort $(wildcard $(REPO_ROOT)/design/*.sv))

FORWARDING_VARIANT ?= canonical

ifeq ($(FORWARDING_VARIANT),canonical)
FORWARDING_SOURCE := $(CANONICAL_FORWARDING)
else ifeq ($(FORWARDING_VARIANT),m2)
FORWARDING_SOURCE := $(M2_FORWARDING)
else
$(error unknown FORWARDING_VARIANT=$(FORWARDING_VARIANT))
endif

VERILOG_SOURCES = \
        $(REGPACK) \
        $(filter-out $(REGPACK) $(CANONICAL_FORWARDING),$(DESIGN_SV)) \
        $(FORWARDING_SOURCE) \
        $(sort $(wildcard $(REPO_ROOT)/design/*.v)) \
        $(REPO_ROOT)/research/week5/rtl/execution_stream_tb.sv

TOPLEVEL = execution_stream_tb
MODULE = test_m2_checker

SIM_BUILD ?= $(REPO_ROOT)/sim_build/week13_m2_$(FORWARDING_VARIANT)

export PYTHONPATH := $(THIS_DIR):$(REPO_ROOT):$(PYTHONPATH)

ifeq ($(SIM),verilator)
COMPILE_ARGS += -Wno-fatal
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
