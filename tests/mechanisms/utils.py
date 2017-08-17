# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import itertools


def matrix(*iterables, **kwargs):
    """
    Generates a matrix of parameters for ``@pytest.mark.parametrize``.

    The matrix is essentially the Cartesian product of the arguments (which should be iterables),
    with the added ability to "flatten" each value by breaking up tuples and recombining them into a
    final flat value.

    To do such recombination, use the ``counts`` argument (tuple) to specify the number of elements
    per value in order. Any count greater than 1 (the default) enables recombination of that value.

    Example::

      x = ('hello', 'goodbye')
      y = ('Linus', 'Richard')
      matrix(x, y) ->
        ('hello', 'Linus'),
        ('hello', 'Richard'),
        ('goodbye', 'Linus'),
        ('goodbye', 'Richard')

      y = (('Linus', 'Torvalds'), ('Richard', 'Stallman'))
      matrix(x, y) ->
        ('hello', ('Linus', 'Torvalds')),
        ('hello', ('Richard', 'Stallman')),
        ('goodbye', ('Linus', 'Torvalds')),
        ('goodbye', ('Richard', 'Stallman'))

      matrix(x, y, counts=(1, 2)) ->
        ('hello', 'Linus', 'Torvalds'),
        ('hello', 'Richard', 'Stallman'),
        ('goodbye', 'Linus', 'Torvalds'),
        ('goodbye', 'Richard', 'Stallman')
    """
    counts = kwargs.get('counts')
    for product in itertools.product(*iterables):
        if counts:
            elements = []
            for value_index, value in enumerate(product):
                try:
                    count = counts[value_index]
                except IndexError:
                    count = 1
                if count == 1:
                    # As is
                    elements.append(value)
                else:
                    # Recombine
                    for element_index in range(count):
                        elements.append(value[element_index])
            yield tuple(elements)
        else:
            yield product
