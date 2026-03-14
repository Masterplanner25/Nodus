Nodus Example Programs

This document contains small example programs demonstrating the Nodus language and runtime features.

Examples focus on:

core language syntax

data structures

control flow

modules

automation patterns

orchestration features

Hello World

The simplest Nodus program.

fn main() {
    print("Hello, world!")
}

Run with:

nodus run hello.nd
Variables and Arithmetic

Basic variable usage.

fn main() {
    let a = 10
    let b = 20

    let result = a + b

    print(result)
}
Functions

Functions are declared with fn.

fn add(a, b) {
    return a + b
}

fn main() {
    let value = add(3, 4)
    print(value)
}
Conditional Logic

Example of if control flow.

fn main() {
    let value = 10

    if value > 5 {
        print("greater")
    } else {
        print("smaller")
    }
}
Loops

Basic iteration example.

fn main() {
    let i = 0

    while i < 5 {
        print(i)
        i = i + 1
    }
}
Lists

Creating and using lists.

fn main() {
    let numbers = [1, 2, 3, 4]

    let i = 0

    while i < len(numbers) {
        print(numbers[i])
        i = i + 1
    }
}
Maps / Records

Using key-value structures.

fn main() {
    let user = {
        name: "Alice",
        age: 30
    }

    print(user.name)
}
Modules

Importing modules from the standard library.

import std:strings

fn main() {
    let value = strings.lower("HELLO")

    print(value)
}
File System Example

Reading a file.

import std:fs

fn main() {
    let contents = fs.read("data.txt")

    print(contents)
}
JSON Example

Using the JSON module.

import std:json

fn main() {
    let data = {
        name: "Alice",
        score: 42
    }

    let text = json.encode(data)

    print(text)
}
Coroutines

Example of coroutine behavior.

fn worker() {
    print("start")
    yield
    print("resume")
}

fn main() {
    let w = worker()

    run(w)
}
Channels

Message passing example.

import std:async

fn producer(ch) {
    ch.send(1)
    ch.send(2)
}

fn consumer(ch) {
    let value = ch.recv()
    print(value)
}

fn main() {
    let ch = async.channel()

    spawn producer(ch)
    spawn consumer(ch)
}
Task Graph

Simple orchestration example.

goal process_data {

    task load {
        run load_file()
    }

    task transform {
        run transform_data()
        after load
    }

    task save {
        run save_results()
        after transform
    }
}

This example shows a basic dependency-driven workflow.

Workflow Example

Workflow orchestration.

workflow pipeline {

    step fetch {
        run fetch_data()
    }

    step process {
        run process_data()
        after fetch
    }

    step publish {
        run publish_results()
        after process
    }
}

Workflows allow complex automation pipelines.

Event Handling

Listening for runtime events.

import std:runtime

fn main() {
    runtime.on("task_complete", fn(event) {
        print(event.task)
    })
}
Using the CLI Tools

Nodus includes several development tools.

View AST:

nodus ast program.nd

View bytecode:

nodus dis program.nd

Format code:

nodus fmt program.nd

Run validation:

nodus check program.nd
Project Example

Typical project structure.

project/
 ├─ nodus.toml
 ├─ main.nd
 └─ lib/
     └─ helpers.nd

Example module:

export fn greet(name) {
    return "Hello " + name
}

Usage:

import lib:helpers

fn main() {
    print(helpers.greet("Alice"))
}
Automation Example

A small automation script.

import std:fs
import std:strings

fn main() {

    let files = fs.list("logs")

    let i = 0

    while i < len(files) {

        let name = files[i]

        if strings.ends_with(name, ".log") {
            print(name)
        }

        i = i + 1
    }
}
Example Philosophy

Example programs should be:

small

readable

idiomatic

realistic

Examples should demonstrate how Nodus is intended to be used in automation and orchestration environments.