# Initial tables
init_table_1 = {
  "table_name": "initial_table",
  "root_url": "init",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "integer"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

init_table_2 = {
  "table_name": "initial_table_2",
  "root_url": "init_two",
  "enums": {"animals": ["cat", "dog"]},
  "comments": "This is initial_table_2. This is a comment to test that comments work",
  "constraints": {"unique": {"unique_col_one_and_two_pair": ["col_one", "col_two"]}},
  "columns": {
    "col_one": {
      "data_type": "varchar",
      "char_len": 255,
      "primary_key": True,
      "comments": "Testing to ensure working comments in table creation."
    },
    "col_two": {
      "data_type": "animals"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

# Creation test tables

create_table_1 = {
  "table_name": "create_table_100000",
  "root_url": "create-table",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "integer"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_2 = {
  "table_name": "create_table_2",
  "root_url": "init",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "integer"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_3 = {
  "table_name": "initial_table",
  "root_url": "create-table-3",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "integer"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_4 = {
  "table_name": "create_table_4",
  "root_url": "create-table-4"
}

create_table_5 = {
  "table_name": "create_table_5",
  "root_url": "create-table-5",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar"
    }
  }
}

create_table_6 = {
  "table_name": "create_table_6",
  "root_url": "create-table-6",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "integer"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_7 = {
  "table_name": "create_table_7",
  "root_url": "create-table-7",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "data_type": "SERIAL"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_8 = {
  "table_name": "create_table_8",
  "root_url": "create-table-8",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "null": True,
      "data_type": "SERIAL"
    },
    "col_three": {
      "null": True,
      "data_type": "integer"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_9 = {
  "table_name": "create_table_9",
  "root_url": "create-table-9",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "data_type": "SERIAL"
    },
    "col_three": {
      "null": True,
      "foreign_key": True,
      "data_type": "integer",
      "reference_table": "initial_table",
      "reference_column": "initial_table_id",
      "on_event": "on delete",
      "event_action": "CASCADE"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}

create_table_10 = {
  "table_name": "create_table_10",
  "root_url": "create-table-10",
  "columns": {
    "col_one": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    },
    "col_two": {
      "data_type": "SERIAL"
    },
    "col_three": {
      "null": False,
      "foreign_key": True,
      "data_type": "integer",
      "reference_table": "initial_table",
      "reference_column": "initial_table_id",
      "on_event": "on delete",
      "event_action": "set null"
    },
    "col_four": {
      "null": False,
      "data_type": "boolean",
      "default": True
    },
    "col_five": {
      "null": True,
      "data_type": "varchar",
      "char_len": 255
    }
  }
}
