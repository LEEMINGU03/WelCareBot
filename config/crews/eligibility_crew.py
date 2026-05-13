from pathlib import Path
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew

_CONFIG = Path(__file__).parent.parent / "config"


@CrewBase
class EligibilityCrew:
    agents_config = str(_CONFIG / "agents.yaml")
    tasks_config = str(_CONFIG / "tasks.yaml")

    @agent
    def eligibility_agent(self) -> Agent:
        return Agent(config=self.agents_config["eligibility_agent"])  # type: ignore

    @task
    def eligibility_task(self) -> Task:
        return Task(config=self.tasks_config["eligibility_task"])  # type: ignore

    @crew
    def crew(self) -> Crew:
        agent = self.eligibility_agent()
        task_ = self.eligibility_task()
        task_.agent = agent
        return Crew(
            agents=[agent],
            tasks=[task_],
            process=Process.sequential,
            verbose=True,
        )
