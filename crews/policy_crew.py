from pathlib import Path
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew
from crewai_tools import SerperDevTool, ScrapeWebsiteTool

_CONFIG = Path(__file__).parent.parent / "config"


@CrewBase
class PolicySearchCrew:
    agents_config = str(_CONFIG / "agents.yaml")
    tasks_config = str(_CONFIG / "tasks.yaml")

    @agent
    def policy_researcher_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["policy_researcher_agent"],  # type: ignore
            tools=[SerperDevTool(), ScrapeWebsiteTool()],
        )

    @task
    def policy_search_task(self) -> Task:
        return Task(config=self.tasks_config["policy_search_task"])  # type: ignore

    @crew
    def crew(self) -> Crew:
        agent = self.policy_researcher_agent()
        search = self.policy_search_task()
        search.agent = agent
        return Crew(
            agents=[agent],
            tasks=[search],
            process=Process.sequential,
            verbose=True,
        )
