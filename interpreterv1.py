from intbase import InterpreterBase, ErrorType
from brewparse import parse_program

class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)   # call InterpreterBase's constructor
        self.variables = {} # dict to hold variables
    
    def run(self, program):
        ast = parse_program(program=program, plot=True)

        # check if main function exists
        main = self.find_main(ast)
        if not main:
            super().error(
                ErrorType.NAME_ERROR,
                "No main() function was found",
            )

        self.run_func(main)

    def find_main(self, ast):
        for f in ast.dict["functions"]:
            if f.dict["name"] == "main":
                return f
        return None
    
    def run_func(self, function):
        for statement in function.dict["statements"]:
            self.run_statement(statement)

    def run_statement(self, statement):
        if statement.elem_type == "vardef":
            self.do_definition(statement)
        elif statement.elem_type == "=":
            self.do_assignment(statement)
        elif statement.elem_type == "fcall":
            self.do_func_call(statement)

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
        if func_name == "print":
            self.do_print(function)
        elif func_name == "inputi":
            input = self.do_input_call(function)
            return input
        else:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_name} has not been defined",
            )   

    def do_print(self, print_node): 
        text = ""
        for arg in print_node.dict['args']:
            text += str(self.evaluate_expression(arg))
        # output using the output() method in InterpreterBase base class
        super().output(text)

    def do_input_call(self, input_node):
        # inputi can only have max of 1 parameter
        args = input_node.dict["args"]
        if len(args) > 1:
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible types for arithmetic operation",
            )
        
        # output prompt if there is one
        if len(args) == 1:
            prompt = self.evaluate_expression(args[0])
            super().output(prompt)
        
        input = int(super().get_input())
        return input

    def evaluate_expression(self, expression):
        if expression.elem_type == "int":
            return(expression.dict["val"])
        elif expression.elem_type == "string":
            return(expression.dict["val"])
        elif expression.elem_type == "fcall":
            return self.do_func_call(expression)
        elif (expression.elem_type == "+") or (expression.elem_type == "-"):
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
        
    def eval_binary_op(self, expression):
        if expression.elem_type == "+":
            op1 = expression.dict["op1"]
            op2 = expression.dict["op2"]
            op1_val = self.evaluate_expression(op1)
            op2_val = self.evaluate_expression(op2)
            # check for valid types for arithmetic
            if isinstance(op1_val, int) and isinstance(op2_val, int):
                return op1_val + op2_val
            else:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible types for arithmetic operation",
                ) 

        elif expression.elem_type == "-":
            op1 = expression.dict["op1"]
            op2 = expression.dict["op2"]
            op1_val = self.evaluate_expression(op1)
            op2_val = self.evaluate_expression(op2)
            # check for valid types for arithmetic
            if isinstance(op1_val, int) and isinstance(op2_val, int):
                return op1_val - op2_val
            else:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible types for arithmetic operation",
                ) 


def main():
    # with open("v1/fails/test_input.br") as f:
    #     program = f.read()
    program = """
    def main(){
        var a;
        a = inputi("Enter a number");
        print(a);
    }
    """

    interpreter = Interpreter()
    interpreter.run(program)

if __name__ == "__main__":
    main()