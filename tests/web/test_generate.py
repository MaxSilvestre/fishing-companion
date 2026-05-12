"""Tests for src.web.generate (helpers; main() runs an HTTP call so is not unit-tested)."""

from __future__ import annotations

import subprocess

import pytest

from src.web.generate import detect_repo_url


class TestDetectRepoUrl:
    def test_uses_github_actions_env_var(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "octocat/hello-world")
        assert detect_repo_url() == "https://github.com/octocat/hello-world"

    def test_parses_https_remote(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout="https://github.com/maxime/fishing-companion.git\n",
                stderr="",
            )

        monkeypatch.setattr("src.web.generate.subprocess.run", fake_run)
        assert detect_repo_url() == "https://github.com/maxime/fishing-companion"

    def test_parses_ssh_remote(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout="git@github.com:maxime/fishing-companion.git\n",
                stderr="",
            )

        monkeypatch.setattr("src.web.generate.subprocess.run", fake_run)
        assert detect_repo_url() == "https://github.com/maxime/fishing-companion"

    def test_returns_none_when_git_fails(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd=args)

        monkeypatch.setattr("src.web.generate.subprocess.run", fake_run)
        assert detect_repo_url() is None

    def test_returns_none_for_non_github_remote(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=0,
                stdout="https://gitlab.com/maxime/fishing-companion.git\n",
                stderr="",
            )

        monkeypatch.setattr("src.web.generate.subprocess.run", fake_run)
        assert detect_repo_url() is None
