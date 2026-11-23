from portal import app

if __name__ == '__main__':
    result = app.test_cli_runner().invoke(args=['preparar-db'])
    print(result.output)
    raise SystemExit(result.exit_code)

