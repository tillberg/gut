package main

import (
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestCommonPathPrefix(t *testing.T) {
	assert := assert.New(t)
	assert.Equal("", CommonPathPrefix())
	assert.Equal("", CommonPathPrefix(""))
	assert.Equal("hello", CommonPathPrefix("hello"))
	assert.Equal("hello/bob", CommonPathPrefix("hello/bob"))
	assert.Equal("/hello/bob", CommonPathPrefix("/hello/bob"))
	assert.Equal("/bob", CommonPathPrefix("/bob", "/bob"))
	assert.Equal("hello/bob", CommonPathPrefix("hello/bob", "hello/bob"))
	assert.Equal("/hello/bob", CommonPathPrefix("/hello/bob", "/hello/bob"))
	assert.Equal("/hello/", CommonPathPrefix("/hello/bob", "/hello/sally"))
	assert.Equal("/", CommonPathPrefix("/say/hello/bob", "/yell/hello/bob"))
	assert.Equal("", CommonPathPrefix("/say/hello/bob", "./yell/hello/bob"))
	assert.Equal("/say/", CommonPathPrefix("/say/hello/bob", "/say/hello/sally", "/say/hi/"))
}
