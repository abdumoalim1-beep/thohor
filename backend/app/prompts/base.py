from dataclasses import dataclass

from app.providers.ai.base import AIMessage, AIRole


@dataclass(frozen=True)
class PromptTemplate:
    """Every production prompt lives here as one of these — never as an
    inline string in business logic — so it carries a name/version/
    schema_version that gets logged on every ai_executions row."""

    name: str
    version: str
    schema_version: str
    system: str
    user_template: str

    def render(self, **context: str) -> list[AIMessage]:
        return [
            AIMessage(role=AIRole.system, content=self.system),
            AIMessage(role=AIRole.user, content=self.user_template.format(**context)),
        ]
