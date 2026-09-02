from app.model.authentication.person import Person
from app.repository.authentication.base_repo import BaseRepo

class PersonRepository(BaseRepo):
    model = Person