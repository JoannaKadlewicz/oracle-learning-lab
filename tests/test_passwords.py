from oracle_lab.auth.passwords import (
    DUMMY_HASH,
    PasswordPolicy,
    hash_password,
    load_common_passwords,
    needs_rehash,
    verify_password,
)
from oracle_lab.resources import COMMON_PASSWORDS


def test_hash_round_trip_and_format():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$32768$8$1$") and verify_password("correct horse battery", h)
    assert not verify_password("wrong", h) and hash_password("x" * 12) != hash_password("x" * 12)


def test_old_parameters_need_rehash():
    assert needs_rehash("scrypt$16384$8$1$AAAA$BBBB") and not needs_rehash(hash_password("abcdefghijkl"))


def test_malformed_hashes_never_raise():
    for bad in ["", "garbage", "scrypt$x$8$1$AAAA$BBBB", "bcrypt$1$2$3$AAAA$BBBB", "scrypt$32768$8$1$!!$!!", "scrypt$1$8$1$AAAA"]:
        assert verify_password("anything", bad) is False
        assert needs_rehash(bad)


def test_old_parameters_still_verify():
    import base64
    import hashlib

    salt = b"0123456789abcdef"
    key = hashlib.scrypt(b"old password!", salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
    old = f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"
    assert verify_password("old password!", old) and not verify_password("nope", old)


def test_dummy_hash_never_verifies():
    assert not verify_password("anything at all", DUMMY_HASH)


def test_policy():
    p = PasswordPolicy(frozenset({"passwordpassword"}))
    assert p.problems("short", "a@b.c") == ["Use at least 12 characters."]
    assert p.problems("PasswordPassword", "a@b.c") == ["This password is too common. Pick something less predictable."]
    assert p.problems("me@example.org", "me@example.org") == ["Don't use your email address as the password."]
    assert p.problems("a fine long passphrase", "a@b.c") == []
    assert p.problems("x" * 129, "a@b.c") == ["Use at most 128 characters."]
    assert p.problems(" ME@example.org ", "me@Example.org") == ["Don't use your email address as the password."]


def test_shipped_common_list_loads():
    common = load_common_passwords(COMMON_PASSWORDS)
    assert "password" in common and len(common) > 5000
    assert not any(line.startswith("#") or line == "" for line in common)
