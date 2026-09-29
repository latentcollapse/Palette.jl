// Package relayctl reads relay's INI-style config. See SPEC.md, "relayctl: config".
package relayctl

import "errors"

// Config maps section name to key to value. Keys outside any section are in section "".
type Config map[string]map[string]string

// ParseError reports the 1-based line of the first malformed line.
type ParseError struct {
	Line int
	Msg  string
}

func (e *ParseError) Error() string { return e.Msg }

func Parse(text string) (Config, error) {
	return nil, errors.New("Parse: not implemented")
}
