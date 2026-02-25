"""PHP language pack — rules for all sieves."""

from __future__ import annotations

from codesieve.langs import LanguagePack, register_lang_pack

_pack = LanguagePack()

register_lang_pack("php", _pack)
