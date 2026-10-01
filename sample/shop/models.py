# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.db import models

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin


class Category(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=100)


class Product(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=100)
    price = models.DecimalField('Price', max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
