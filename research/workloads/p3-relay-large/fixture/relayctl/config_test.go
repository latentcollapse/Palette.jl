package relayctl

import (
	"errors"
	"reflect"
	"testing"
)

func mustParse(t *testing.T, text string) Config {
	t.Helper()
	c, err := Parse(text)
	if err != nil {
		t.Fatalf("Parse(%q): %v", text, err)
	}
	return c
}

func expect(t *testing.T, text string, want Config) {
	t.Helper()
	if got := mustParse(t, text); !reflect.DeepEqual(got, want) {
		t.Fatalf("Parse(%q)\n got %v\nwant %v", text, got, want)
	}
}

func TestSectionsAndKeys(t *testing.T) {
	expect(t, "[db]\npath = /var/relay.db\n[api]\nport=8080\n",
		Config{"db": {"path": "/var/relay.db"}, "api": {"port": "8080"}})
}

func TestTopLevelKeys(t *testing.T) {
	expect(t, "name = relay\n[x]\na=1\n", Config{"": {"name": "relay"}, "x": {"a": "1"}})
}

func TestEmptyInput(t *testing.T) {
	expect(t, "", Config{})
	expect(t, "\n\n   \n", Config{})
}

func TestCommentsAndBlankLines(t *testing.T) {
	expect(t, "; top\n# also\n\n[s]\n  ; indented comment\nk = v\n", Config{"s": {"k": "v"}})
}

func TestInlineTextAfterValueIsKept(t *testing.T) {
	expect(t, "[s]\nurl = http://h/#frag ; not a comment\n", Config{"s": {"url": "http://h/#frag ; not a comment"}})
}

func TestKeysAndSectionsAreLowercasedAndTrimmed(t *testing.T) {
	expect(t, "[ DB ]\n  Path  =  x y  \n", Config{"db": {"path": "x y"}})
}

func TestOnlyFirstEqualsSplits(t *testing.T) {
	expect(t, "[s]\nexpr = a=b\n", Config{"s": {"expr": "a=b"}})
}

func TestEmptyValue(t *testing.T) {
	expect(t, "[s]\nk =\n", Config{"s": {"k": ""}})
}

func TestLastDuplicateWins(t *testing.T) {
	expect(t, "[s]\nk=1\nk=2\n[s]\nk=3\nj=4\n", Config{"s": {"k": "3", "j": "4"}})
}

func TestContinuationLines(t *testing.T) {
	expect(t, "[s]\nhosts = a\n  b\n\tc\nnext = 1\n", Config{"s": {"hosts": "a\nb\nc", "next": "1"}})
}

func TestEmptySection(t *testing.T) {
	expect(t, "[empty]\n[s]\nk=v\n", Config{"empty": {}, "s": {"k": "v"}})
}

func TestCRLF(t *testing.T) {
	expect(t, "[s]\r\nk = v\r\n", Config{"s": {"k": "v"}})
}

func lineOf(t *testing.T, text string) int {
	t.Helper()
	_, err := Parse(text)
	var pe *ParseError
	if !errors.As(err, &pe) {
		t.Fatalf("Parse(%q): want a *ParseError, got %v", text, err)
	}
	return pe.Line
}

func TestErrorsNameTheLine(t *testing.T) {
	cases := map[string]int{
		"[s]\nk=v\nnot a pair\n": 3,
		"[s\nk=v\n":              1,
		"[]\n":                   1,
		"[s]\n= v\n":             2,
		"  indented first\n":     1,
	}
	for text, want := range cases {
		if got := lineOf(t, text); got != want {
			t.Errorf("Parse(%q): error on line %d, want %d", text, got, want)
		}
	}
}
