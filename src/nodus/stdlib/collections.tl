fn list_sum(nums) {
    let total = 0
    for (let i = 0; i < len(nums); i = i + 1) {
        total = total + nums[i]
    }
    return total
}

fn list_last(nums) {
    return nums[len(nums) - 1]
}

fn first(items) {
    return items[0]
}

fn last(items) {
    return items[len(items) - 1]
}

fn push(items, value) {
    return items + [value]
}

fn has_key(map, key) {
    let ks = keys(map)
    for (let i = 0; i < len(ks); i = i + 1) {
        if (ks[i] == key) {
            return true
        }
    }
    return false
}
