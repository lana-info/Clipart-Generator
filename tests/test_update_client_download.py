"""Скачивание обновления клиентом: таймауты, ретрай и причины (жалоба 2026-10-31).

До фикса `download` качал 243 МБ чанками по 1 МБ с таймаутом 20 с на сокет-операцию
и сваливал любую сеть в общий текст «Не удалось скачать обновление». После: чанки
256 КБ, таймаут фазы скачивания 120 с, одна автоматическая повторная попытка при
транзиентном сбое и конкретная причина в сообщении.
"""
import hashlib
import http.client
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from urllib import error

import update_client as uc
from update_client import UpdateClient, UpdateError, UpdateRelease

SETUP_BYTES = b"VibixImages-Setup-3.2.54" * 4096  # ~98 КБ уникального содержимого


def make_client(tmp_path, attempts=2):
    client = UpdateClient(
        license_client=SimpleNamespace(
            product_id="clipart-generator",
            _validated_base_url=lambda: "https://services.etsyneuroclub.com/licenses",
        ),
        current_version="3.2.53",
        download_directory=tmp_path / "downloads",
        platform_id="windows-x64",
    )
    monkeypatch_attempts(client, attempts)
    return client


def monkeypatch_attempts(client, attempts):
    object.__setattr__(client.lifecycle_policy, "download_attempts", attempts)


def release(content: bytes) -> UpdateRelease:
    return UpdateRelease(
        version="3.2.54",
        filename="VibixImages-Setup-3.2.54.exe",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        download_url="https://services.etsyneuroclub.com/licenses/downloads/token",
        notes="",
        correlation_id="",
    )


class FakeResponse:
    def __init__(self, content: bytes, fail_reads: int = 0, declared: int | None = None):
        self.headers = {"Content-Length": str(len(content) if declared is None else declared)}
        self._content = content
        self._fail_reads = fail_reads
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        if self._fail_reads > 0:
            self._fail_reads -= 1
            raise TimeoutError("timed out")
        chunk = self._content[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


class FakeOpener:
    """Скриптованный открыватель: поведение на каждую попытку скачивания."""

    script: list = []
    opened = 0

    def open(self, req, timeout=None):
        FakeOpener.opened += 1
        behavior = FakeOpener.script.pop(0) if FakeOpener.script else ("ok", SETUP_BYTES)
        kind, payload = behavior
        if kind == "timeout":
            # Полный Content-Length, но каждый read рвётся по таймауту.
            return FakeResponse(payload, fail_reads=10 ** 9)
        if kind == "http500":
            raise error.HTTPError(req.full_url, 500, "boom", hdrs={}, fp=None)
        if kind == "http403":
            raise error.HTTPError(req.full_url, 403, "forbidden", hdrs={}, fp=None)
        if kind == "short":
            # Объявленный размер — полный, а поток обрывается на половине.
            return FakeResponse(payload[: len(payload) // 2], declared=len(payload))
        return FakeResponse(payload)


@pytest.fixture
def scripted_opener(monkeypatch):
    FakeOpener.script = []
    FakeOpener.opened = 0
    monkeypatch.setattr(uc.request, "build_opener", lambda *args, **kwargs: FakeOpener())
    return FakeOpener


def make_release_for(content):
    return release(content)


def test_transient_timeout_is_retried_and_then_succeeds(tmp_path, scripted_opener):
    client = make_client(tmp_path)
    content = SETUP_BYTES
    release_ = release(content)
    scripted_opener.script = [("timeout", content), ("ok", content)]
    result = client.download(release_)
    assert result.read_bytes() == content
    assert FakeOpener.opened == 2
    assert not list((tmp_path / "downloads").glob("*.part"))


def test_persistent_timeout_names_the_cause_and_cleans_up(tmp_path, scripted_opener):
    client = make_client(tmp_path)
    release_ = release(SETUP_BYTES)
    scripted_opener.script = [("timeout", SETUP_BYTES), ("timeout", SETUP_BYTES)]
    with pytest.raises(UpdateError) as raised:
        client.download(release_)
    assert "Соединение прервалось" in str(raised.value)
    assert FakeOpener.opened == 2
    assert not list((tmp_path / "downloads").glob("*.part"))
    assert not (tmp_path / "downloads" / release_.filename).exists()


def test_http_500_is_retried_http_403_is_not(tmp_path, scripted_opener):
    client = make_client(tmp_path)
    content = SETUP_BYTES
    release_ = release(content)
    scripted_opener.script = [("http500", None), ("ok", content)]
    assert client.download(release_).read_bytes() == content
    scripted_opener.script = [("http403", None)]
    with pytest.raises(UpdateError) as raised:
        client.download(release_)
    assert "HTTP 403" in str(raised.value)
    assert FakeOpener.opened == 3  # 500-ретрай (2) + 403 без ретрая (1)


def test_short_file_and_bad_checksum_do_not_retry(tmp_path, scripted_opener):
    client = make_client(tmp_path)
    release_ = release(SETUP_BYTES)
    scripted_opener.script = [("short", SETUP_BYTES)]
    with pytest.raises(UpdateError) as raised:
        client.download(release_)
    assert "не полностью" in str(raised.value)
    scripted_opener.script = [("ok", b"tampered")]  # размер совпал? нет — другой длины
    # Для проверки контрольной суммы нужен размер как у релиза, но другой байтовый состав.
    tampered = bytes(b ^ 0xFF for b in SETUP_BYTES)
    scripted_opener.script = [("ok", tampered)]
    tampered_release = UpdateRelease(
        version="3.2.54",
        filename="VibixImages-Setup-3.2.54.exe",
        size=len(tampered),
        sha256=hashlib.sha256(SETUP_BYTES).hexdigest(),  # ожидаем оригинал
        download_url="https://services.etsyneuroclub.com/licenses/downloads/token",
        notes="",
        correlation_id="",
    )
    with pytest.raises(UpdateError) as raised:
        client.download(tampered_release)
    assert "Контрольная сумма" in str(raised.value)
    assert FakeOpener.opened == 2  # ни одна из двух ошибок не ретраится


def test_negative_control_without_retry_policy(tmp_path, scripted_opener, monkeypatch):
    """Реверт политики к одной попытке: транзиентный таймаут больше не ретраится."""
    client = make_client(tmp_path, attempts=1)
    release_ = release(SETUP_BYTES)
    scripted_opener.script = [("timeout", SETUP_BYTES), ("ok", SETUP_BYTES)]
    with pytest.raises(UpdateError):
        client.download(release_)
    assert FakeOpener.opened == 1


class ResetResponse(FakeResponse):
    """Поток, который рвётся посреди скачивания не таймаутом, а сбросом/обрывом соединения."""

    def __init__(self, content, failure):
        super().__init__(content)
        self._failure = failure

    def read(self, size):
        if self._failure is not None:
            failure, self._failure = self._failure, None
            raise failure
        return super().read(size)


def _scripted_failures(monkeypatch, *failures):
    """Первые попытки рвутся перечисленными исключениями, следующая проходит."""
    queue = list(failures)
    opened = []

    class Opener:
        def open(self, req, timeout=None):
            opened.append(1)
            return ResetResponse(SETUP_BYTES, queue.pop(0) if queue else None)

    monkeypatch.setattr(uc.request, "build_opener", lambda *args, **kwargs: Opener())
    return opened


@pytest.mark.parametrize("failure", [
    ConnectionResetError(10054, "Удалённый хост принудительно разорвал соединение"),
    ConnectionAbortedError(10053, "Программа на вашем хосте разорвала соединение"),
    http.client.IncompleteRead(b"partial", 100),
], ids=["reset", "aborted", "incomplete-read"])
def test_connection_drop_mid_download_is_retried_like_a_timeout(tmp_path, monkeypatch, failure):
    client = make_client(tmp_path)
    opened = _scripted_failures(monkeypatch, failure)
    assert client.download(release(SETUP_BYTES)).read_bytes() == SETUP_BYTES
    assert len(opened) == 2
    assert not list((tmp_path / "downloads").glob("*.part"))


def test_persistent_connection_drop_is_a_named_update_error_not_a_raw_exception(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    _scripted_failures(monkeypatch, http.client.IncompleteRead(b"x", 9), ConnectionResetError(10054, "reset"))
    with pytest.raises(UpdateError) as raised:
        client.download(release(SETUP_BYTES))
    assert "Соединение прервалось" in str(raised.value)
    assert not list((tmp_path / "downloads").glob("*.part"))


def test_final_file_held_by_antivirus_is_retried_instead_of_failing_the_update(tmp_path, monkeypatch):
    """Windows: свежий установщик на секунду занят сканером — os.replace даёт WinError 32/5."""
    client = make_client(tmp_path)
    _scripted_failures(monkeypatch)
    monkeypatch.setattr(uc.time, "sleep", lambda seconds: None)
    real_replace = os.replace
    refusals = []

    def locked_twice(source, destination):
        if len(refusals) < 2:
            refusals.append(1)
            raise PermissionError(32, "Процесс не может получить доступ к файлу")
        return real_replace(source, destination)

    monkeypatch.setattr(uc.os, "replace", locked_twice)
    assert client.download(release(SETUP_BYTES)).read_bytes() == SETUP_BYTES
    assert len(refusals) == 2


def test_final_file_locked_for_good_is_a_named_error_and_leaves_no_part_file(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    _scripted_failures(monkeypatch)
    monkeypatch.setattr(uc.time, "sleep", lambda seconds: None)

    def always_locked(source, destination):
        raise PermissionError(32, "Процесс не может получить доступ к файлу")

    monkeypatch.setattr(uc.os, "replace", always_locked)
    with pytest.raises(UpdateError) as raised:
        client.download(release(SETUP_BYTES))
    assert "занят" in str(raised.value)
    assert not list((tmp_path / "downloads").glob("*.part"))
