# 父类
class Animal:
    def __init__(self, name):
        self.name = name
        print(f"Animal {name} 被创建")

# 子类
class Dog(Animal):
    def __init__(self, name, breed):
        # 调用父类的构造函数
        super().__init__(name)
        # 子类特有的初始化
        self.breed = breed
        print(f"Dog {name} ({breed}) 被创建")

# 使用
my_dog = Dog("旺财", "金毛")
my_animal = Animal("mao")
# 输出：
# Animal 旺财 被创建
# Dog 旺财 (金毛) 被创建
print(my_animal.name)