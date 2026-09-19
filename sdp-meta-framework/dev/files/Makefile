# ==============================================================================
# sdp-meta-framework-bundle — CI/CD deploy gate
# ==============================================================================
# Purpose: avoid deploying/running the whole bundle on every commit. Instead,
# inspect which paths changed in the diff range and only run the steps that
# are relevant to that change:
#
#   conf/**, resources/sdp_meta_onboarding_job.yml,        -> deploy bundle, then
#   resources/sdp_meta_pipelines.yml changed                  re-run sdp_meta_onboarding
#
#   framework/** changed                                    -> deploy bundle, then run
#                                                               wheel_build_and_deploy
#                                                               (rebuilds wheel, uploads
#                                                               to the UC Volume,
#                                                               refreshes specs)
#
# `databricks bundle deploy` itself is idempotent and only syncs resource
# definitions + the bundle's own wheel artifact -- it never executes anything.
# The `bundle run` calls below are what actually execute the onboarding /
# wheel jobs, and only fire when their trigger paths changed.
#
# ------------------------------------------------------------------------------
# GitHub Actions usage (in a workflow step):
#   - run: |
#       make ci-deploy TARGET=dev \
#         BASE_REF=${{ github.event.before }} \
#         HEAD_REF=${{ github.sha }}
#
#   For pull_request triggers, prefer:
#     BASE_REF=${{ github.event.pull_request.base.sha }}
#     HEAD_REF=${{ github.event.pull_request.head.sha }}
#   (make sure the checkout step uses fetch-depth: 0 so both SHAs exist)
#
# Jenkins usage (in a Jenkinsfile stage):
#   sh 'make ci-deploy TARGET=dev BASE_REF=$GIT_PREVIOUS_SUCCESSFUL_COMMIT HEAD_REF=$GIT_COMMIT'
#   (falls back to HEAD~1 via BASE_REF default below when
#   GIT_PREVIOUS_SUCCESSFUL_COMMIT is unset, e.g. on the first-ever run)
#
# Local usage (diff against main):
#   make ci-deploy TARGET=dev
# ==============================================================================

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# ------------------------------------------------------------------------------
# Config -- override via env vars or `make VAR=value`
# ------------------------------------------------------------------------------
TARGET   ?= dev
BASE_REF ?= $(shell git merge-base HEAD origin/main 2>/dev/null || git rev-parse HEAD~1 2>/dev/null || echo HEAD)
HEAD_REF ?= HEAD

CHANGED_FILES_TMP := /tmp/sdp_meta_bundle_changed_files_$(TARGET).txt

# Extended regex tested against changed file paths (relative to repo root).
# No trailing anchors needed -- `git diff --name-only` emits exact paths only.
PIPELINE_REGEX  := ^conf/|^resources/sdp_meta_onboarding_job\.yml|^resources/sdp_meta_pipelines\.yml
FRAMEWORK_REGEX := ^framework/

.PHONY: help
help:
	@echo "Targets:"
	echo "  make ci-deploy TARGET=dev [BASE_REF=<sha>] [HEAD_REF=<sha>]"
	echo "      Gated entrypoint for CI/CD. Diffs BASE_REF..HEAD_REF and only"
	echo "      deploys/runs the resources relevant to what changed."
	echo ""
	echo "  make changed-files [BASE_REF=<sha>] [HEAD_REF=<sha>]"
	echo "      Print the files changed in the diff range (debug helper)."
	echo ""
	echo "  make deploy TARGET=dev             Unconditional 'databricks bundle deploy'"
	echo "  make run-onboarding TARGET=dev      Unconditional 'bundle run sdp_meta_onboarding'"
	echo "  make run-wheel-build TARGET=dev     Unconditional 'bundle run wheel_build_and_deploy'"
	echo "  make run-all-pipelines TARGET=dev   Unconditional 'bundle run run_all_pipelines'"

.PHONY: changed-files
changed-files:
	@git diff --name-only $(BASE_REF) $(HEAD_REF)

# ------------------------------------------------------------------------------
# Gated CI/CD entrypoint -- the only target CI should call on every commit
# ------------------------------------------------------------------------------
.PHONY: ci-deploy
ci-deploy:
	@echo "==> Diffing $(BASE_REF)..$(HEAD_REF)"
	git diff --name-only $(BASE_REF) $(HEAD_REF) > $(CHANGED_FILES_TMP)
	echo "==> Changed files:"
	sed 's/^/    /' $(CHANGED_FILES_TMP)
	if ! grep -Eq '$(PIPELINE_REGEX)' $(CHANGED_FILES_TMP) && ! grep -Eq '$(FRAMEWORK_REGEX)' $(CHANGED_FILES_TMP); then
		echo "==> No relevant paths (conf/, resources/sdp_meta_onboarding_job.yml, resources/sdp_meta_pipelines.yml, framework/) changed. Skipping deploy."
		rm -f $(CHANGED_FILES_TMP)
		exit 0
	fi
	echo "==> Relevant changes detected. Running: databricks bundle deploy --target $(TARGET)"
	databricks bundle deploy --target $(TARGET)
	if grep -Eq '$(PIPELINE_REGEX)' $(CHANGED_FILES_TMP); then
		echo "==> conf/ or pipeline job specs changed -> refreshing onboarding specs (sdp_meta_onboarding)"
		databricks bundle run sdp_meta_onboarding --target $(TARGET)
	fi
	if grep -Eq '$(FRAMEWORK_REGEX)' $(CHANGED_FILES_TMP); then
		echo "==> framework/ changed -> rebuilding + uploading wheel (wheel_build_and_deploy)"
		databricks bundle run wheel_build_and_deploy --target $(TARGET)
	fi
	rm -f $(CHANGED_FILES_TMP)
	echo "==> ci-deploy complete."

# ------------------------------------------------------------------------------
# Unconditional building blocks -- useful for manual/ad-hoc invocation
# ------------------------------------------------------------------------------
.PHONY: deploy
deploy:
	@databricks bundle deploy --target $(TARGET)

.PHONY: run-onboarding
run-onboarding:
	@databricks bundle run sdp_meta_onboarding --target $(TARGET)

.PHONY: run-wheel-build
run-wheel-build:
	@databricks bundle run wheel_build_and_deploy --target $(TARGET)

.PHONY: run-all-pipelines
run-all-pipelines:
	@databricks bundle run run_all_pipelines --target $(TARGET)
