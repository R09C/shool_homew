from g4f.client import Client
from g4f.models import DeepInfraChat

client = Client()
response = client.chat.completions.create(
    model="deepseek-prover-v2-671b",
    messages=[
        {
            "role": "user",
            "content": """
вот синтаксис:

from dataclasses import dataclass


class Manipulator:
    pass


@dataclass
class Object:
    name: str


class Location:
    pass


def find(obj: Object) -> Location:
    pass


def pick(manipulator: Manipulator, obj: Object) -> Manipulator:
    pass


def leave_object(manipulator: Manipulator) -> Manipulator:
    pass


def move(manipulator: Manipulator, location: Location) -> Manipulator:
    pass

    
    вот примеры:
    
# Примеры сценариев для домена Robot

Перемещение объекта из одной локации в другую

```python
manipulator = Manipulator()
obj = Object(name="Box")
start_location = find(obj)
manipulator = move(manipulator, start_location)
manipulator = pick(manipulator, obj)
target_location = Location()
manipulator = move(manipulator, target_location)
manipulator = leave_object(manipulator)
res = target_location
```

Перемещение двух объектов в разные локации

```python
manipulator = Manipulator()
obj1 = Object(name="Box1")
obj2 = Object(name="Box2")
start_location1 = find(obj1)
start_location2 = find(obj2)

# Перемещение первого объекта
manipulator = move(manipulator, start_location1)
manipulator = pick(manipulator, obj1)
target_location1 = Location()
manipulator = move(manipulator, target_location1)
manipulator = leave_object(manipulator)

# Перемещение второго объекта
manipulator = move(manipulator, start_location2)
manipulator = pick(manipulator, obj2)
target_location2 = Location()
manipulator = move(manipulator, target_location2)
manipulator = leave_object(manipulator)

res = [target_location1, target_location2]
```

Сортировка объектов по локациям

```python
manipulator = Manipulator()
objects = [Object(name=f"Object{i}") for i in range(3)]
locations = [Location() for _ in range(3)]

for obj, location in zip(objects, locations):
    start_location = find(obj)
    manipulator = move(manipulator, start_location)
    manipulator = pick(manipulator, obj)
    manipulator = move(manipulator, location)
    manipulator = leave_object(manipulator)

res = locations
```

Сбор всех объектов в одну локацию

```python
manipulator = Manipulator()
objects = [Object(name=f"Object{i}") for i in range(3)]
target_location = Location()

for obj in objects:
    start_location = find(obj)
    manipulator = move(manipulator, start_location)
    manipulator = pick(manipulator, obj)
    manipulator = move(manipulator, target_location)
    manipulator = leave_object(manipulator)

res = target_location
```
создай еще 2 сложных комбинированных сценария, которые используют все функции и классы из синтаксиса. Сценарии должны быть сложными, но не слишком длинными. Каждый сценарий должен быть в отдельном блоке кода с комментариями, объясняющими шаги.
         """,
        }
    ],
    provider=DeepInfraChat,
)
print(response.choices[0].message.content)
