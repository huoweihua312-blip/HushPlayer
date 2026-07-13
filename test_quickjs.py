import quickjs


ctx = quickjs.Context()

result = ctx.eval("""
function hello(name) {
    return "你好，" + name;
}

hello("HushPlayer");
""")

print(result)