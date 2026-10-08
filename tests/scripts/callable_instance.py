class Main:
    async def __call__(self) -> None:
        print("callable instance ran")


main = Main()
