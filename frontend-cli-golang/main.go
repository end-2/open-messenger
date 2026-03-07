package main

import (
	"os"

	"open-messenger/frontend-cli-golang/cli"
)

func main() {
	cli.Run(os.Args[1:])
}
