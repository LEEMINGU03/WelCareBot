from pathlib import Path
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew

_CONFIG = Path(__file__).parent.parent / "config"


@CrewBase
class IntakeCrew:
    agents_config = str(_CONFIG / "agents.yaml")
    tasks_config = str(_CONFIG / "tasks.yaml")

    @agent
    def intake_agent(self) -> Agent:
        return Agent(config=self.agents_config["intake_agent"])  # type: ignore

    @task
    def intake_task(self) -> Task:
        return Task(config=self.tasks_config["intake_task"])  # type: ignore

    @crew
    def crew(self) -> Crew:
        agent = self.intake_agent()
        intake = self.intake_task()
        intake.agent = agent
        return Crew(
            agents=[agent],
            tasks=[intake],
            process=Process.sequential,
            verbose=True,
        )
