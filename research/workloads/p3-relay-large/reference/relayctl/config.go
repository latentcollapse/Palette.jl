// Package relayctl reads relay's INI-style config. See SPEC.md, "relayctl: config".
package relayctl

import "strings"

// Config maps section name to key to value. Keys outside any section are in section "".
type Config map[string]map[string]string

// ParseError reports the 1-based line of the first malformed line.
type ParseError struct {
	Line int
	Msg  string
}

func (e *ParseError) Error() string { return e.Msg }

func Parse(text string) (Config, error) {
	c := Config{}
	section, lastKey := "", ""
	for i, line := range strings.Split(text, "\n") {
		line = strings.TrimSuffix(line, "\r")
		t := strings.TrimSpace(line)
		bad := func(msg string) error { return &ParseError{Line: i + 1, Msg: msg} }
		switch {
		case t == "" || t[0] == ';' || t[0] == '#':
			continue
		case (line[0] == ' ' || line[0] == '\t') && lastKey != "":
			c[section][lastKey] += "\n" + t
		case t[0] == '[':
			if !strings.HasSuffix(t, "]") {
				return nil, bad("unclosed section")
			}
			name := strings.ToLower(strings.TrimSpace(t[1 : len(t)-1]))
			if name == "" {
				return nil, bad("empty section name")
			}
			section, lastKey = name, ""
			if c[section] == nil {
				c[section] = map[string]string{}
			}
		default:
			k, v, ok := strings.Cut(t, "=")
			k = strings.ToLower(strings.TrimSpace(k))
			if !ok || k == "" {
				return nil, bad("expected key = value")
			}
			if c[section] == nil {
				c[section] = map[string]string{}
			}
			c[section][k] = strings.TrimSpace(v)
			lastKey = k
		}
	}
	return c, nil
}
