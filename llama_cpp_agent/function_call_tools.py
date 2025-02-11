import json
from typing import Type

from llama_cpp import LlamaGrammar
from pydantic import BaseModel

from .output_parser import parse_json_response_with_file_string, sanitize_json_string, parse_json_response
from .gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import format_model_and_field_name, \
    generate_gbnf_grammar_and_documentation


class LlamaCppFunctionTool:
    def __init__(self, pydantic_model: Type[BaseModel], has_field_string=False, **additional_parameters):
        self.model = pydantic_model
        self.look_for_field_string = has_field_string
        self.additional_parameters = additional_parameters if additional_parameters else {}

    def __call__(self, *args, **kwargs):
        return self.model(**kwargs)


class LlamaCppFunctionToolRegistry:
    def __init__(self):
        self.tool_root = "function"
        self.tool_rule_content = "function_parameters"
        self.model_prefix = "Function"
        self.fields_prefix = "Function Parameters"
        self.function_tools = {}
        self.function_tools_containing_field_string = {}
        self.grammar = None
        self.grammar_documentation = None
        self.gbnf_grammar = None

    def register_function_tool(self, function_tool: LlamaCppFunctionTool):
        function_name = format_model_and_field_name(function_tool.model.__name__)
        if function_tool.look_for_field_string:
            self.function_tools_containing_field_string[function_name] = function_tool
        else:
            self.function_tools[function_name] = function_tool

    def get_function_tool(self, function_name: str):
        if function_name in self.function_tools:
            return self.function_tools[function_name]
        elif function_name in self.function_tools_containing_field_string:
            return self.function_tools_containing_field_string[function_name]
        else:
            return None

    def finalize(self):
        pydantic_function_models = []
        look_file_string = False
        for function_tool in self.function_tools.values():
            pydantic_function_models.append(function_tool.model)
            if function_tool.look_for_field_string:
                look_file_string = True
        for function_tool in self.function_tools_containing_field_string.values():
            pydantic_function_models.append(function_tool.model)
            if function_tool.look_for_field_string:
                look_file_string = True
        gbnf_grammar, documentation = generate_gbnf_grammar_and_documentation(
            pydantic_function_models, look_file_string, self.tool_root, self.tool_rule_content, self.model_prefix,
            self.fields_prefix)

        self.grammar = LlamaGrammar.from_string(gbnf_grammar, verbose=False)
        self.grammar_documentation = documentation
        self.gbnf_grammar = gbnf_grammar

    def get_grammar(self):
        return self.grammar

    def get_documentation(self):
        return self.grammar_documentation

    def handle_function_call(self, function_call_response: str):
        try:
            for name, tool in self.function_tools_containing_field_string.items():

                if name in function_call_response:
                    function_call, content = parse_json_response_with_file_string(function_call_response)
                    function_call["function_parameters"]["file_string"] = content

                    output = self.intern_function_call(function_call, with_file_string=True)
                    return output

            function_call = parse_json_response(function_call_response)
            output = self.intern_function_call(function_call)
            return output

        except AttributeError as e:
            return f"Error: {e}"

    def intern_function_call(self, function_call: dict, with_file_string=False):
        if with_file_string:
            function_tool = self.function_tools_containing_field_string[function_call["function"]]
        else:
            function_tool = self.function_tools[function_call["function"]]
        try:
            cls = function_tool.model
            call_parameters = function_call["function_parameters"]
            call = cls(**call_parameters)
            output = call.run(**function_tool.additional_parameters)
            return output
        except AttributeError as e:
            return f"Error: {e}"