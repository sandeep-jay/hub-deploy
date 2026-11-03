from pathlib import Path

from jupyter_ai_acp_client.base_acp_persona import BaseAcpPersona as BaseACPPersona
from jupyter_ai_persona_manager import PersonaDefaults

_here = Path(__file__).parent.resolve()
_icon_svg = _here / "icon.svg"


class BioRouterACPPersona(BaseACPPersona):
    def __init__(self, *args, **kwargs):
        executable = ["biorouter", "acp"]
        super().__init__(*args, executable=executable, **kwargs)

    @property
    def defaults(self) -> PersonaDefaults:
        return PersonaDefaults(
            name="BioRouter",
            description="BioRouter as an ACP agent persona.",
            avatar_path=str(_icon_svg),
            system_prompt="unused",
        )
