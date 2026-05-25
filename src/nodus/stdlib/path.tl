fn join(parts) {
    let out = parts[0]
    let i = 1
    while (i < len(parts)) {
        out = path_join(out, parts[i])
        i = i + 1
    }
    return out
}

fn dirname(path) {
    return path_dirname(path)
}

fn basename(path) {
    return path_basename(path)
}

fn ext(path) {
    return path_ext(path)
}

fn stem(path) {
    return path_stem(path)
}
