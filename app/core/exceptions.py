from fastapi import HTTPException, status


class CredentialsException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(HTTPException):
    def __init__(self, detail: str = "Acesso negado"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundException(HTTPException):
    def __init__(self, entity: str = "Recurso"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity} não encontrado")


class ConflictException(HTTPException):
    def __init__(self, detail: str = "Conflito"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
