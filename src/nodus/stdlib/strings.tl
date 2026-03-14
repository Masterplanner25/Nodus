fn repeat(s, n) {
    let out = ""
    let i = 0
    while (i < n) {
        out = out + s
        i = i + 1
    }
    return out
}

fn is_blank(s) {
    return len(s) == 0
}

fn join(items, sep) {
    let out = ""
    let i = 0
    while (i < len(items)) {
        if (i > 0) {
            out = out + sep
        }
        out = out + str(items[i])
        i = i + 1
    }
    return out
}
