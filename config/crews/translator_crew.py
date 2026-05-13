from pathlib import Path
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew

_CONFIG = Path(__file__).parent.parent / "config"


@CrewBase
class TranslatorCrew:
    agents_config = str(_CONFIG / "agents.yaml")
    tasks_config = str(_CONFIG / "tasks.yaml")

    @agent
    def translator_agent(self) -> Agent:
        return Agent(config=self.agents_config["translator_agent"])  # type: ignore

    @task
    def translate_task(self) -> Task:
        return Task(config=self.tasks_config["translate_task"])  # type: ignore

    @crew
    def crew(self) -> Crew:
        agent = self.translator_agent()
        translate = self.translate_task()
        translate.agent = agent
        return Crew(
            agents=[agent],
            tasks=[translate],
            process=Process.sequential,
            verbose=True,
        )
