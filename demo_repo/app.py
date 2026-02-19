def parse_input(value):
    return int(value)

def safe_divide(a, b):
    return a / b

def compute(data):
    nums = [parse_input(x) for x in data]
    return safe_divide(sum(nums), len(nums))

if __name__ == "__main__":
    dataset = ["10", "abc", "30"]
    print(compute(dataset))
