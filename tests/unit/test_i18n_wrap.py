"""The template wrapper must never change what English users see."""
import re

import pytest
from django.template import engines

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('i18n_wrap', Path(__file__).resolve().parents[2] / 'scripts' / 'i18n_wrap.py')
wrap = importlib.util.module_from_spec(spec); sys.modules['i18n_wrap'] = wrap; spec.loader.exec_module(wrap)


def render(src, ctx):
    return engines['django'].from_string(src).render(ctx)


def norm(html):
    return re.sub(r'\s+', ' ', html).strip()


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


CTX = {'name': 'Asha', 'n': 3, 'p': Obj(first='Raman', count=5), 'items': ['a', 'b'], 'when': __import__('datetime').date(2030, 1, 5),
       'html': '<b>x</b>', 'user': Obj(get_full_name='Priya N'), 'flag': True}

SAMPLES = [
    '<h1>Welcome back</h1>',
    '<p>Hello {{ name }}, you have {{ n }} new messages.</p>',
    '<p>Showing {{ p.count }} of {{ n }} patients — 100% done</p>',
    '<p>Date: {{ when|date:"M d, Y" }} at the clinic</p>',
    '<p>Unsafe {{ html }} and safe {{ html|safe }} text</p>',
    '<input type="text" placeholder="Search patients..." title="Find a patient">',
    '<input placeholder="Patient\'s name">',
    '<button class="x" onclick="go()">Save &amp; Close</button>',
    '<div>{% if flag %}Active{% else %}Inactive{% endif %} user</div>',
    '<ul>{% for i in items %}<li>Item {{ i }} is ready</li>{% endfor %}</ul>',
    '<p>She said "hello" to {{ name }}</p>',
    '<label for="a">Amount (₹)</label><span>Total: ₹{{ n }}</span>',
    '<script>var s = "Not translated {{ name }}";</script><p>After script</p>',
    '<style>.a:after{content:"Skip me"}</style><p>Text</p>',
    '<pre>  keep   this  </pre><p>and this</p>',
    '<textarea placeholder="Notes here">{{ name }}</textarea>',
    '<!-- a comment with words --><p>Visible</p>',
    '{# django comment words #}<p>Visible</p>',
    '<a href="/x/" aria-label="Open the thing">Open</a>',
    '<p>Rating: {{ n }}/5 stars — {{ user.get_full_name }}</p>',
    '<img src="a.png" alt="Company logo"><p>{{ name }}</p>',
    '<td>{{ n }}</td><td>Pending</td>',
    '<div x-data="{ go() { fetch(u).then(r => r.json()).then(d => { this.x = d; }); } }" @click="a => b">Open menu</div>',
    '<button @click="open = !open; if (n > 1) { x = 2 }" title=\'Toggle "it"\'>Toggle</button>',
    '<p>Line one\n      line two   spaced</p>',
]


@pytest.mark.parametrize('src', SAMPLES)
def test_wrapped_template_renders_identically_in_english(src):
    wrapped = wrap.transform(src)
    assert norm(render('{% load i18n %}' + wrapped, CTX)) == norm(render(src, CTX)), wrapped


def test_wrapper_leaves_code_and_brand_names_alone():
    out = wrap.transform('<script>var a = "Hello world";</script><style>.x{content:"Words"}</style><p>SpinalCure</p><p>WhatsApp</p>')
    assert 'trans' not in out


def test_variable_sentences_use_blocktranslate_with_named_placeholders():
    out = wrap.transform('<p>Hello {{ user.get_full_name }}, you have {{ n }} items.</p>')
    assert '{% blocktranslate trimmed with get_full_name=user.get_full_name n=n %}' in out
    assert 'Hello {{ get_full_name }}, you have {{ n }} items.' in out and '%(' not in out


def test_load_i18n_is_inserted_after_extends_and_once():
    out = wrap.transform('{% extends "base.html" %}\n{% block c %}<p>Hello there</p>{% endblock %}')
    assert out.startswith('{% extends "base.html" %}') and out.count('{% load i18n %}') == 1
    again = wrap.transform(out)
    assert again == out                                                              # idempotent
    assert wrap.transform('{% load static i18n %}<p>Hi there</p>').count('load i18n') == 0


def test_bom_and_mojibake_safe_read():
    assert not wrap.transform('{% extends "b.html" %}<p>Text here</p>').startswith('﻿')


def test_arrow_functions_in_attributes_are_never_treated_as_text():
    src = '<div x-data="{ go() { fetch(u).then(r => r.json()).then(d => { this.x = d; }); } }">Hello there</div>'
    out = wrap.transform(src)
    assert 'x-data="{ go() { fetch(u).then(r => r.json()).then(d => { this.x = d; }); } }"' in out      # attribute intact
    assert out.count('{% trans') == 1 and '{% trans "Hello there" %}' in out
