FROM public.ecr.aws/lambda/python:3.12
COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir "${LAMBDA_TASK_ROOT}[dev]" --target "${LAMBDA_TASK_ROOT}"
COPY app ${LAMBDA_TASK_ROOT}/app
COPY handler.py ${LAMBDA_TASK_ROOT}/
CMD ["handler.main"]
