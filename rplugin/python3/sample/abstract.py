from abc import ABC, abstractmethod


class AbstractClassExample(ABC):

    @abstractmethod
    def do_something(self):
        print("wilson: from super {}".format(type(self).__name__))
        print("Some implementation!")


class AnotherSubclass(AbstractClassExample):

    def do_something(self):
        print("wilson from sub: {}".format(type(self).__name__))
        super().do_something()
        print("The enrichment from AnotherSubclass")


x = AnotherSubclass()
x.do_something()
