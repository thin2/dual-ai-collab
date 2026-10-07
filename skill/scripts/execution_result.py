"""Shared result contract for execution backends; acceptance remains separate."""
from tasks_store import CliError

RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["result", "summary", "files_changed", "acceptance", "verification", "notes"],
    "properties": {
        "result": {"type": "string", "enum": ["DONE", "BLOCKED"]},
        "summary": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "acceptance": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "status", "note"],
                "properties": {
                    "criterion": {"type": "string"},
                    "status": {"type": "string", "enum": ["PASS", "FAIL", "UNCLEAR"]},
                    "note": {"type": "string"},
                },
            },
        },
        "verification": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "outcome"],
                "properties": {"command": {"type": "string"}, "outcome": {"type": "string"}},
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_result(value, schema, path="result"):
    """Validate the object/array/string subset used by the worker result schema."""
    kind = schema.get('type')
    expected = {'object': dict, 'array': list, 'string': str}.get(kind)
    if expected is None or not isinstance(value, expected):
        raise CliError(f'执行结果字段类型错误: {path}')
    if 'enum' in schema and value not in schema['enum']:
        raise CliError(f'执行结果字段取值错误: {path}')
    if kind == 'object':
        properties = schema.get('properties', {})
        if any(key not in value for key in schema.get('required', [])):
            raise CliError(f'执行结果缺少必需字段: {path}')
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise CliError(f'执行结果包含未知字段: {path}')
        for key in value.keys() & properties.keys():
            validate_result(value[key], properties[key], f'{path}.{key}')
    elif kind == 'array':
        for index, item in enumerate(value):
            validate_result(item, schema['items'], f'{path}[{index}]')
