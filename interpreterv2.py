from intbase import InterpreterBase, ErrorType
from brewparse import parse_program
# from debug_utils import debug_logger, debug_logger_with_return_val, debug, info

class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)   # call InterpreterBase's constructor
        self.variables = {} # dict to hold variables
    
    def run(self, program):
        ast = parse_program(program=program)

        # store all functions. Key will store (name, arity)
        self.functions = {}
        self.define_functions(ast)

        # check if main function exists
        if ("main", 0) not in self.functions:
            super().error(
                ErrorType.NAME_ERROR,
                "No main() function was found",
            )

        self.run_func(self.functions[("main", 0)], [])

    def define_functions(self, ast):
        for f in ast.dict["functions"]:
            name = f.dict["name"]
            arity = len(f.dict["args"])
            self.functions[(name, arity)] = f
        
    # support functions with parameters
    def run_func(self, function, args):
        # function scopes -> save old scope when we return from func call
        old_scope = self.variables
        self.variables = {}

        # add function args to function's variables
        params = function.dict["args"]
        for param, arg in zip(params, args):
            self.variables[param.dict["name"]] = arg

        ret_val = None
        for statement in function.dict["statements"]:
            ret_val = self.run_statement(statement)
            if isinstance(ret_val, tuple) and ret_val[0] is True:
                ret_val = ret_val[1]
                break
            
        self.variables = old_scope
        return ret_val

    def run_statement(self, statement):
        if statement.elem_type == "vardef":
            self.do_definition(statement)
        elif statement.elem_type == "=":
            self.do_assignment(statement)
        elif statement.elem_type == "fcall":
            self.do_func_call(statement)
        elif statement.elem_type == "return":
            return self.do_return(statement)
        elif statement.elem_type == "if":
            return self.do_if(statement)
        elif statement.elem_type == "while":
            return self.do_while(statement)

    def do_while(self, while_node):
        # evaluate condition and check if bool
        cond = self.evaluate_expression(while_node.dict["condition"])

        if not type(cond) == bool:
           super().error(
               ErrorType.TYPE_ERROR,
               f"If condition does not evaluate to a boolean",
           )
        
        while cond:
            for statement in while_node.dict["statements"]:
                ret_val = self.run_statement(statement)
                if ret_val is not None:
                    return ret_val
                cond = self.evaluate_expression(while_node.dict["condition"])
        return None

    def do_definition(self, variable):
        var_name = variable.dict["name"]
        # return error if redefinition is attempted
        if var_name in self.variables:
            super().error(
                ErrorType.NAME_ERROR,
                f"Variable {var_name} defined more than once",
            )
        self.variables[var_name] = None
    
    def do_assignment(self, variable):
        var_name = variable.dict["var"]
        # variable must be defined beforehand, return error
        if var_name not in self.variables:
            super().error(
                ErrorType.NAME_ERROR,
                f"Variable {var_name} has not been defined",
            )
        expression = variable.dict["expression"]
        val = self.evaluate_expression(expression)
        self.variables[var_name] = val

    def do_func_call(self, function):
        func_name = function.dict["name"]
        func_args = function.dict["args"]
        if func_name == "print":
            self.do_print(function)
            return None
        elif func_name == "inputi":
            input = self.do_inputi_call(function)
            return input
        elif func_name == "inputs":
            input = self.do_inputs_call(function)
            return input
        else:
            # check for user-defined function
            if (func_name, len(func_args)) not in self.functions:
                super().error(
                    ErrorType.NAME_ERROR,
                    f"Function {func_name} has not been defined",
                )   
            
            evaluated_args = [self.evaluate_expression(arg) for arg in func_args]
            return self.run_func(self.functions[(func_name, len(func_args))], evaluated_args)

    def do_return(self, statement):
        expression = statement.dict["expression"]
        # tuple (ifReturnCalled, val) to differentiate whether or not return was called
        if expression is None:
            return (True, None)
        return (True, self.evaluate_expression(expression))

    def do_if(self, if_node):
        # evaluate condition and check if bool
        cond = self.evaluate_expression(if_node.dict["condition"])

        if not type(cond) == bool:
           super().error(
               ErrorType.TYPE_ERROR,
               f"If condition does not evaluate to a boolean",
           )
        
        if cond:
            for statement in if_node.dict["statements"]:
                ret_val = self.run_statement(statement)
                if ret_val is not None:
                    return ret_val
        else:
            else_statements = if_node.dict["else_statements"]
            if else_statements:
                for statement in else_statements:
                    ret_val = self.run_statement(statement)
                    if ret_val is not None:
                        return ret_val
        
        return None
    
    def do_print(self, print_node): 
        text = ""
        for arg in print_node.dict['args']:
            # convert to lowercase if boolean
            val = self.evaluate_expression(arg)
            if type(val) == bool:
                text += "true" if val else "false"
            else:
                text += str(val)
        # output using the output() method in InterpreterBase base class
        super().output(text)

    def do_inputi_call(self, input_node):
        # inputi can only have max of 1 parameter
        args = input_node.dict["args"]
        if len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR,
                "Too many arguments given for inputi",
            )
        
        # output prompt if there is one
        if len(args) == 1:
            prompt = self.evaluate_expression(args[0])
            super().output(prompt)
        
        input = int(super().get_input())
        return input
    
    def do_inputs_call(self, input_node):
        # inputs can only have max of 1 parameter
        args = input_node.dict["args"]
        if len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR,
                "Too many arguments given for inputs",
            )
        
        # output prompt if there is one
        if len(args) == 1:
            prompt = self.evaluate_expression(args[0])
            super().output(prompt)
        
        input = str(super().get_input())
        return input

    def evaluate_expression(self, expression):
        unary_operations  = {'neg', '!'}
        binary_operations = {'+', '-', '*', '/', '==', '!=', '>', '>=', '<', '<=', '||', '&&' }
        if expression.elem_type == "int":
            return(expression.dict["val"])
        elif expression.elem_type == "string":
            return(expression.dict["val"])
        elif expression.elem_type == "bool":
            return(expression.dict["val"])
        elif expression.elem_type == "nil":
            return None # represent nil as python None type
        elif expression.elem_type == "fcall":
            return self.do_func_call(expression)
        elif expression.elem_type in unary_operations:
            return(self.eval_unary_op(expression))
        elif expression.elem_type in binary_operations:
            return(self.eval_binary_op(expression))
        elif expression.elem_type == "qname":
            var_name = expression.dict["name"]
            # variable must be defined beforehand, return error
            if var_name not in self.variables:
                super().error(
                    ErrorType.NAME_ERROR,
                    f"Variable {var_name} has not been defined",
                )
            return self.variables[var_name]
    
    def eval_unary_op(self, expression):
        op_type = expression.elem_type
        op1 = expression.dict["op1"]
        op1_val = self.evaluate_expression(op1)

        if op_type == "neg":
            if not type(op1_val) == int:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for negation operator",
                )
            return -op1_val
        
        elif op_type == "!":
            if not type(op1_val) == bool:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for logical NOT operator",
                )
            return not op1_val
             
    def eval_binary_op(self, expression):
        op_type = expression.elem_type
        op1 = expression.dict["op1"]
        op2 = expression.dict["op2"]
        op1_val = self.evaluate_expression(op1)
        op2_val = self.evaluate_expression(op2)

        # for + handle integer addition or string concatenation
        if op_type == "+":
            if (type(op1_val) == int and type(op2_val) == int) or (
                type(op1_val) == str and type(op2_val) == str
            ):
                return op1_val + op2_val
            else:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible types for addition operation",
                )

        elif op_type in { "-", "*", "/", "<", "<=", ">", ">=" }:
            if not (type(op1_val) == int and type(op2_val) == int):
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible types for binary operator. Expected 2 integers",
                ) 
            if op_type == "-": return op1_val - op2_val
            elif op_type == "*": return op1_val * op2_val
            elif op_type == "/": return op1_val // op2_val
            elif op_type == "<": return op1_val < op2_val
            elif op_type == "<=": return op1_val <= op2_val
            elif op_type == ">": return op1_val > op2_val
            elif op_type == ">=": return op1_val >= op2_val
        
        elif op_type in { "==", "!=" }:
            # compare both type and value
            equal_types = False
            if type(op1_val) == type(op2_val):
                equal_types = True
            if not equal_types:
                return op_type == "!="
            equal_values = op1_val == op2_val
            return equal_values if op_type == "==" else not equal_values
        
        elif op_type in { "&&", "||" }:
            if not (type(op1_val) == bool and type(op2_val) == bool):
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible types for logical operation",
                )
            if op_type == "&&": return op1_val and op2_val
            elif op_type == "||": return op1_val or op2_val