from itertools import chain
from . import cards as CardDB, rules
from .actions import Damage, Deaths, Destroy, Heal, Morph, Play, Shuffle, SetCurrentHealth
from .aura import Aura
from .entity import Entity, boolean_property, int_property
from .enums import CardType, PlayReq, Race, Rarity, Zone
from .managers import CardManager
from .targeting import is_valid_target
from .utils import CardList


THE_COIN = "GAME_005"


def Card(id, data=None):
	if data is None:
		data = getattr(CardDB, id)
	subclass = {
		CardType.HERO: Hero,
		CardType.MINION: Minion,
		CardType.SPELL: Spell,
		CardType.ENCHANTMENT: Enchantment,
		CardType.WEAPON: Weapon,
		CardType.HERO_POWER: HeroPower,
	}[data.type]
	if subclass is Spell and data.secret:
		subclass = Secret
	return subclass(id, data)


class BaseCard(Entity):
	Manager = CardManager
	has_deathrattle = boolean_property("has_deathrattle")
	atk = int_property("atk")
	max_health = int_property("max_health")
	cost = int_property("cost")

	def __init__(self, id, data):
		self.data = data
		super().__init__()
		self.auras = []
		self.requirements = data.requirements.copy()
		self.id = id
		self.controller = None
		self.aura = False
		self.heropower_damage = 0
		self.silenced = False
		self.spellpower = 0
		self.turns_in_play = 0
		self._zone = Zone.INVALID
		self.tags.update(data.tags)

	def __str__(self):
		return self.name

	def __repr__(self):
		return "<%s (%r)>" % (self.__class__.__name__, self.__str__())

	def __eq__(self, other):
		if isinstance(other, BaseCard):
			return self.id.__eq__(other.id)
		elif isinstance(other, str):
			return self.id.__eq__(other)
		return super().__eq__(other)

	@property
	def game(self):
		return self.controller.game

	@property
	def zone(self):
		return self._zone

	@zone.setter
	def zone(self, value):
		self._set_zone(value)

	def _set_zone(self, value):
		old = self.zone
		if old:
			self.logger.debug("%r moves from %r to %r", self, old, value)
		assert old != value
		caches = {
			Zone.HAND: self.controller.hand,
			Zone.DECK: self.controller.deck,
			Zone.GRAVEYARD: self.controller.graveyard
		}
		if caches.get(old) is not None:
			caches[old].remove(self)
		if caches.get(value) is not None:
			caches[value].append(self)
		self._zone = value

		if value == Zone.PLAY:
			if hasattr(self.data.scripts, "aura"):
				auras = self.data.scripts.aura
				if not hasattr(auras, "__iter__"):
					auras = (auras, )
				for aura in auras:
					aura = Aura(aura, source=self)
					aura.summon()
		else:
			for aura in self.auras:
				aura.to_be_destroyed = True

	def buff(self, target, buff, **kwargs):
		"""
		Summon \a buff and apply it to \a target
		If keyword arguments are given, attempt to set the given
		values to the buff. Example:
		player.buff(target, health=random.randint(1, 5))
		NOTE: Any Card can buff any other Card. The controller of the
		Card that buffs the target becomes the controller of the buff.
		"""
		ret = self.controller.card(buff, self)
		ret.apply(target)
		for k, v in kwargs.items():
			setattr(ret, k, v)
		return ret


class PlayableCard(BaseCard):
	windfury = boolean_property("windfury")

	def __init__(self, id, data):
		self.buffs = CardList()
		self.cant_play = False
		self.entourage = CardList(data.entourage)
		self.has_battlecry = False
		self.has_combo = False
		self.overload = 0
		self.target = None
		self.rarity = Rarity.INVALID
		super().__init__(id, data)

	@property
	def events(self):
		if self.zone == Zone.HAND:
			ret = getattr(self.data.scripts, "in_hand", [])
			if not hasattr(ret, "__iter__"):
				ret = (ret, )
			return ret
		return self.base_events + self._events

	@property
	def deathrattles(self):
		ret = []
		if not self.has_deathrattle:
			return ret
		if hasattr(self.data.scripts, "deathrattle"):
			ret.append(self.data.scripts.deathrattle)
		for buff in self.buffs:
			if buff.has_deathrattle and hasattr(buff.data.scripts, "deathrattle"):
				ret.append(buff.data.scripts.deathrattle)
		return ret

	@property
	def powered_up(self):
		"""
		Returns True whether the card is "powered up".
		Currently, this only applies to some cards which require a minion with a
		specific race on the field.
		"""
		for req in self.data.powerup_requirements:
			for minion in self.controller.field:
				if minion.race == req:
					return True
		return False

	@property
	def entities(self):
		return chain([self], self.buffs)

	@property
	def slots(self):
		return self.buffs

	def _set_zone(self, zone):
		old_zone = self.zone
		super()._set_zone(zone)
		if old_zone == Zone.PLAY and zone not in (Zone.GRAVEYARD, Zone.SETASIDE):
			self.clear_buffs()

	def action(self):
		if self.cant_play:
			self.log("%r play action cannot continue", self)
			return

		kwargs = {}
		if self.target:
			kwargs["target"] = self.target
		elif self.has_target():
			self.log("%r has no target, action exits early", self)
			return

		if self.has_combo and self.controller.combo:
			self.log("Activating %r combo targeting %r", self, self.target)
			actions = self.data.scripts.combo
		elif hasattr(self.data.scripts, "play"):
			self.log("Activating %r action targeting %r", self, self.target)
			actions = self.data.scripts.play
		elif self.choose:
			self.log("Activating %r Choose One: %r", self, self.chosen)
			actions = self.chosen.data.scripts.play
		else:
			actions = []

		if callable(actions):
			actions = actions(self, **kwargs)

		if actions:
			self.game.queue_actions(self, actions)
			# Hard-process deaths after a battlecry.
			# cf. test_knife_juggler()
			self.game.process_deaths()

		if self.overload:
			self.log("%r overloads %s for %i", self, self.controller, self.overload)
			self.controller.overloaded += self.overload

	def clear_buffs(self):
		if self.buffs:
			self.log("Clearing buffs from %r", self)
			for buff in self.buffs[:]:
				buff.destroy()

	def destroy(self):
		return self.game.queue_actions(self, [Destroy(self), Deaths()])

	def _destroy(self):
		"""
		Destroy a card.
		If the card is in PLAY, it is instead scheduled to be destroyed, and it will
		be moved to the GRAVEYARD on the next Death event.
		"""
		if self.zone == Zone.PLAY:
			self.log("Marking %r for imminent death", self)
			self.to_be_destroyed = True
		else:
			self.zone = Zone.GRAVEYARD

	def discard(self):
		self.log("Discarding %r" % (self))
		self.zone = Zone.DISCARD

	def draw(self):
		if len(self.controller.hand) >= self.controller.max_hand_size:
			self.log("%s overdraws and loses %r!", self.controller, self)
			self.discard()
		else:
			self.log("%s draws %r", self.controller, self)
			self.zone = Zone.HAND
			self.controller.cards_drawn_this_turn += 1

	def heal(self, target, amount):
		return self.game.queue_actions(self, [Heal(target, amount)])

	def hit(self, target, amount):
		return self.game.queue_actions(self, [Damage(target, amount)])

	def is_playable(self):
		if self.controller.choice:
			return False
		if not self.controller.current_player:
			return False
		if self.controller.mana < self.cost:
			return False
		if PlayReq.REQ_TARGET_TO_PLAY in self.requirements:
			if not self.targets:
				return False
		if PlayReq.REQ_NUM_MINION_SLOTS in self.requirements:
			if self.requirements[PlayReq.REQ_NUM_MINION_SLOTS] > self.controller.minion_slots:
				return False
		if len(self.controller.opponent.field) < self.requirements.get(PlayReq.REQ_MINIMUM_ENEMY_MINIONS, 0):
			return False
		if len(self.controller.game.board) < self.requirements.get(PlayReq.REQ_MINIMUM_TOTAL_MINIONS, 0):
			return False
		if PlayReq.REQ_ENTIRE_ENTOURAGE_NOT_IN_PLAY in self.requirements:
			if not [id for id in self.entourage if not self.controller.field.contains(id)]:
				return False
		if PlayReq.REQ_WEAPON_EQUIPPED in self.requirements:
			if not self.controller.weapon:
				return False
		if PlayReq.REQ_FRIENDLY_MINION_DIED_THIS_GAME in self.requirements:
			if not self.controller.graveyard.filter(type=CardType.MINION):
				return False
		return True

	def play(self, target=None, choose=None):
		"""
		Queue a Play action on the card.
		"""
		if choose is not None:
			assert choose in self.data.choose_cards
		elif target is not None:
			assert self.has_target()
			assert target in self.targets
		else:
			assert not self.has_target()
		assert self.is_playable()
		assert self.zone == Zone.HAND
		self.game.queue_actions(self.controller, [Play(self, target, choose)])
		return self

	def shuffle_into_deck(self):
		"""
		Shuffle the card into the controller's deck
		"""
		return self.game.queue_actions(self.controller, [Shuffle(self.controller, self)])

	def has_target(self):
		if self.has_combo and PlayReq.REQ_TARGET_FOR_COMBO in self.requirements:
			if self.controller.combo:
				return True
		if PlayReq.REQ_TARGET_IF_AVAILABLE in self.requirements:
			return bool(self.targets)
		if PlayReq.REQ_TARGET_IF_AVAILABLE_AND_DRAGON_IN_HAND in self.requirements:
			if self.controller.hand.filter(race=Race.DRAGON):
				return bool(self.targets)
		return PlayReq.REQ_TARGET_TO_PLAY in self.requirements

	@property
	def targets(self):
		return [card for card in self.game.characters if is_valid_target(self, card)]


class LiveEntity(PlayableCard):
	def __init__(self, *args):
		super().__init__(*args)
		self._to_be_destroyed = False
		self._damage = 0

	@property
	def dead(self):
		return self.zone == Zone.GRAVEYARD or self.to_be_destroyed

	@property
	def to_be_destroyed(self):
		return getattr(self, self.health_attribute) == 0 or self._to_be_destroyed

	@to_be_destroyed.setter
	def to_be_destroyed(self, value):
		self._to_be_destroyed = value


class Character(LiveEntity):
	health_attribute = "health"
	cant_be_targeted_by_opponents = boolean_property("cant_be_targeted_by_opponents")
	immune = boolean_property("immune")
	min_health = boolean_property("min_health")

	def __init__(self, *args):
		self.attacking = False
		self.frozen = False
		self.cant_attack = False
		self.cant_be_targeted_by_abilities = False
		self.cant_be_targeted_by_hero_powers = False
		self.num_attacks = 0
		self.race = Race.INVALID
		super().__init__(*args)

	@property
	def attackable(self):
		return not self.immune

	@property
	def attack_targets(self):
		taunts = []
		for target in self.controller.opponent.field:
			if target.taunt:
				taunts.append(target)
		ret = []
		for target in (taunts if taunts else self.controller.opponent.field):
			if target.attackable:
				ret.append(target)
		if not taunts and self.controller.opponent.hero.attackable:
			ret.append(self.controller.opponent.hero)
		return ret

	def can_attack(self, target=None):
		if not self.zone == Zone.PLAY:
			return False
		if self.cant_attack:
			return False
		if not self.controller.current_player:
			return False
		if not self.atk:
			return False
		if self.exhausted:
			return False
		if self.frozen:
			return False
		if not self.targets:
			return False
		if target is not None and target not in self.targets:
			return False

		return True

	@property
	def max_attacks(self):
		if self.windfury:
			return 2
		return 1

	@property
	def exhausted(self):
		if self.num_attacks >= self.max_attacks:
			return True
		return False

	@property
	def should_exit_combat(self):
		if self.attacking:
			if self.dead or self.zone != Zone.PLAY:
				return True
		return False

	def attack(self, target):
		assert self.can_attack(target)
		self.game.attack(self, target)

	@property
	def damaged(self):
		return bool(self.damage)

	@property
	def damage(self):
		return self._damage

	@damage.setter
	def damage(self, amount):
		amount = max(0, amount)
		dmg = self.damage

		if self.min_health:
			self.log("%r has HEALTH_MINIMUM of %i", self, self.min_health)
			amount = min(amount, self.max_health - self.min_health)

		self._damage = amount

	@property
	def health(self):
		return max(0, self.max_health - self.damage)

	def _hit(self, source, amount):
		if self.immune:
			self.log("%r is immune to %i damage from %r", self, amount, source)
			return 0
		self.damage += amount
		return amount

	@property
	def targets(self):
		if self.zone == Zone.PLAY:
			return self.attack_targets
		return super().targets

	def set_current_health(self, amount):
		return self.game.queue_actions(self, [SetCurrentHealth(self, amount)])


class Hero(Character):
	def __init__(self, id, data):
		self.armor = 0
		self.power = None
		super().__init__(id, data)

	@property
	def slots(self):
		ret = super().slots[:]
		if self.controller.weapon and not self.controller.weapon.exhausted:
			ret.append(self.controller.weapon)
		return ret

	@property
	def entities(self):
		ret = [self]
		if self.power:
			ret.append(self.power)
		if self.controller.weapon:
			ret.append(self.controller.weapon)
		return chain(ret, self.buffs)

	def _set_zone(self, value):
		if value == Zone.PLAY:
			self.controller.hero = self
			if self.data.hero_power:
				self.controller.summon(self.data.hero_power)
		super()._set_zone(value)

	def _hit(self, source, amount):
		if self.armor:
			new_amount = max(0, amount - self.armor)
			self.armor -= min(self.armor, amount)
			amount = new_amount
		return super()._hit(source, amount)


class Minion(Character):
	charge = boolean_property("charge")
	has_inspire = boolean_property("has_inspire")
	stealthed = boolean_property("stealthed")
	taunt = boolean_property("taunt")

	silenceable_attributes = (
		"always_wins_brawls", "aura", "cant_attack", "cant_be_targeted_by_abilities",
		"cant_be_targeted_by_hero_powers", "charge", "divine_shield", "enrage",
		"frozen", "has_deathrattle", "has_inspire", "poisonous", "stealthed",
		"taunt", "windfury",
	)

	def __init__(self, id, data):
		self._enrage = None
		self.always_wins_brawls = False
		self.divine_shield = False
		self.enrage = False
		self.poisonous = False
		super().__init__(id, data)

	@property
	def events(self):
		ret = super().events
		if self.poisonous:
			ret += rules.Poisonous
		return ret

	@property
	def adjacent_minions(self):
		assert self.zone is Zone.PLAY, self.zone
		ret = CardList()
		index = self.controller.field.index(self)
		left = self.controller.field[:index]
		right = self.controller.field[index + 1:]
		if left:
			ret.append(left[-1])
		if right:
			ret.append(right[0])
		return ret

	@property
	def attackable(self):
		if self.stealthed:
			return False
		return super().attackable

	@property
	def asleep(self):
		return self.zone == Zone.PLAY and not self.turns_in_play and not self.charge

	@property
	def exhausted(self):
		if self.asleep:
			return True
		return super().exhausted

	@property
	def slots(self):
		slots = super().slots[:]
		if self.enraged:
			if not self._enrage:
				self._enrage = Enrage(self.data.enrage_tags)
			slots.append(self._enrage)
		return slots

	@property
	def enraged(self):
		return self.enrage and self.damage

	def _set_zone(self, value):
		if value == Zone.PLAY:
			self.controller.field.append(self)

		if self.zone == Zone.PLAY:
			self.log("%r is removed from the field", self)
			self.controller.field.remove(self)
			if self.damage:
				self.damage = 0

		super()._set_zone(value)

	def bounce(self):
		self.log("%r is bounced back to %s's hand", self, self.controller)
		if len(self.controller.hand) == self.controller.max_hand_size:
			self.log("%s's hand is full and bounce fails", self.controller)
			self.destroy()
		else:
			self.zone = Zone.HAND

	def hit(self, target, amount):
		super().hit(target, amount)
		if self.stealthed:
			self.stealthed = False

	def _hit(self, source, amount):
		if self.divine_shield:
			self.divine_shield = False
			self.log("%r's divine shield prevents %i damage.", self, amount)
			return

		return super()._hit(source, amount)

	def morph(self, into):
		return self.game.queue_actions(self, [Morph(self, into)])

	def is_playable(self):
		playable = super().is_playable()
		if len(self.controller.field) >= self.game.MAX_MINIONS_ON_FIELD:
			return False
		return playable

	def silence(self):
		self.log("Silencing %r", self)
		for aura in self.auras:
			aura.to_be_destroyed = True
		self.clear_buffs()

		for attr in self.silenceable_attributes:
			if getattr(self, attr):
				setattr(self, attr, False)

		# Wipe the event listeners
		self._events = []
		self.silenced = True


class Spell(PlayableCard):
	def __init__(self, *args):
		self.immune_to_spellpower = False
		self.receives_double_spelldamage_bonus = False
		super().__init__(*args)

	def hit(self, target, amount):
		if not self.immune_to_spellpower:
			amount = self.controller.get_spell_damage(amount)
		if self.receives_double_spelldamage_bonus:
			amount *= 2
		super().hit(target, amount)


class Secret(Spell):
	@property
	def exhausted(self):
		return not self.controller.current_player

	def _set_zone(self, value):
		if value == Zone.PLAY:
			# Move secrets to the SECRET Zone when played
			value = Zone.SECRET
		if self.zone == Zone.SECRET:
			self.controller.secrets.remove(self)
		if value == Zone.SECRET:
			self.controller.secrets.append(self)
		super()._set_zone(value)

	def is_playable(self):
		# secrets are all unique
		if self.controller.secrets.contains(self):
			return False
		return super().is_playable()

	def reveal(self):
		return self.game.queue_actions(self, [Reveal(self)])


class Enchantment(BaseCard):
	slots = []

	def __init__(self, *args):
		self.aura_source = None
		self.one_turn_effect = False
		self.attack_health_swap = False
		super().__init__(*args)

	def _getattr(self, attr, i):
		if self.attack_health_swap:
			if attr == "atk":
				return self._swapped_atk
			elif attr == "max_health":
				return self._swapped_health
		return super()._getattr(attr, i)

	def _set_zone(self, zone):
		if zone == Zone.PLAY:
			self.owner.buffs.append(self)
		elif zone == Zone.REMOVEDFROMGAME:
			self.owner.buffs.remove(self)
		super()._set_zone(zone)

	def apply(self, target):
		self.log("Applying %r to %r", self, target)
		self.owner = target
		if self.attack_health_swap:
			self._swapped_atk = target.health
			self._swapped_health = target.atk
		if hasattr(self.data.scripts, "apply"):
			self.data.scripts.apply(self, target)
		if hasattr(self.data.scripts, "max_health") or self.attack_health_swap:
			self.log("%r removes all damage from %r", self, target)
			target.damage = 0
		self.zone = Zone.PLAY

	def destroy(self):
		self.log("Destroying buff %r from %r", self, self.owner)
		if hasattr(self.data.scripts, "destroy"):
			self.data.scripts.destroy(self)
		self.zone = Zone.REMOVEDFROMGAME
		if self.aura_source:
			# Clean up the buff from its source auras
			self.aura_source._buffs.remove(self)
	_destroy = destroy


class Enrage(object):
	"""
	Enrage class for Minion.enrage_tags
	Enrage buffs are just a collection of tags for the enraged Minion's slots.
	"""

	def __init__(self, tags):
		CardManager(self).update(tags)

	def _getattr(self, attr, i):
		return i + getattr(self, attr, 0)


class Weapon(rules.WeaponRules, LiveEntity):
	health_attribute = "durability"

	def __init__(self, *args):
		super().__init__(*args)
		self.damage = 0

	@property
	def durability(self):
		return max(0, self.max_durability - self.damage)

	@property
	def max_durability(self):
		ret = self._max_durability
		ret += self._getattr("max_health", 0)
		return max(0, ret)

	@max_durability.setter
	def max_durability(self, value):
		self._max_durability = value

	@property
	def exhausted(self):
		return self.zone == Zone.PLAY and not self.controller.current_player

	def _hit(self, source, amount):
		self.damage += amount
		return amount

	def _set_zone(self, zone):
		if zone == Zone.PLAY:
			if self.controller.weapon:
				self.controller.weapon.destroy()
			self.controller.weapon = self
		elif self.zone == Zone.PLAY:
			self.controller.weapon = None
		super()._set_zone(zone)


class HeroPower(PlayableCard):
	def _set_zone(self, value):
		if value == Zone.PLAY:
			if self.controller.hero.power:
				self.controller.hero.power.destroy()
			self.controller.hero.power = self
			self.exhausted = False
		super()._set_zone(value)

	def activate(self):
		actions = self.data.scripts.activate
		if callable(actions):
			kwargs = {}
			if self.target:
				kwargs["target"] = self.target
			actions = actions(self, **kwargs)

		ret = []
		if actions:
			ret += self.game.queue_actions(self, actions)

		for minion in self.controller.field.filter(has_inspire=True):
			if not hasattr(minion.data.scripts, "inspire"):
				raise NotImplementedError("Missing inspire script for %r" % (minion))
			actions = minion.data.scripts.inspire
			if actions:
				ret += self.game.queue_actions(self, actions)

		return ret

	def hit(self, target, amount):
		amount += self.controller.heropower_damage
		amount *= (self.controller.hero_power_double + 1)
		super().hit(target, amount)

	def is_playable(self):
		return False

	def play(self, target=None):
		raise NotImplementedError

	def use(self, target=None):
		assert self.is_usable()
		self.log("%s uses hero power %r on %r", self.controller, self, target)

		if self.has_target():
			assert target
			self.target = target

		ret = self.activate()

		self.exhausted = True
		self.controller.times_hero_power_used_this_game += 1
		self.controller.used_mana += self.cost
		self.target = None

		return ret

	def is_usable(self):
		if self.exhausted:
			return False
		return super().is_playable()
